/*
 * TCP-CC-001 sender implementation (revised)
 * ------------------------------------------------------------
 * This program establishes a single TCP connection to 192.168.88.21:5204
 * and continuously streams data while a second thread samples the
 * kernel TCP_INFO structure on the same socket.
 *
 * Features required by the experiment design:
 *   • One connected socket used by both the sender and sampler threads.
 *   • A continuously supplying sender thread that handles partial sends.
 *   • A concurrent sampler thread performing a single‑row CSV snapshot of
 *     raw TCP_INFO fields at a configurable interval (default 1 ms).
 *   • Finite, configurable workload duration (seconds) supplied on the
 *     command line; a value of 0 runs indefinitely.
 *   • Graceful shutdown – after the duration expires the threads exit,
 *     logs are flushed and closed, and the process terminates without
 *     external signals.
 *   • SIGPIPE‑safe behaviour (SIGPIPE ignored, MSG_NOSIGNAL used).
 *   • Clean CSV files with a single header line and one row per event.
 *   • Explicit error reporting to stderr.
 */

#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <pthread.h>
#include <time.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <linux/tcp.h>
#include <stddef.h>  /* for offsetof() */
#include <stdint.h>
#include <inttypes.h>
#include <stdatomic.h>
#include <stdbool.h>

/* -----------------------------------------------------------------
 * Configuration constants – can be overridden at compile time via -D
 * ----------------------------------------------------------------- */
static const char *REMOTE_ADDR = "192.168.88.21";   /* receiver address */
static const int   REMOTE_PORT = 5204;               /* receiver port */
static const size_t SEND_BUF_SIZE = 64 * 1024;       /* 64 KB payload per send */
static const long   SAMPLE_INTERVAL_NS = 1e6;        /* 1 ms default interval */

/* -----------------------------------------------------------------
 * Global state shared between threads
 * ----------------------------------------------------------------- */
static int sock_fd = -1;
static FILE *app_log_fp    = NULL;  /* CSV for send events */
static FILE *tcpinfo_log_fp = NULL; /* CSV for TCP_INFO snapshots */
/* termination flag – atomic for safe cross‑thread visibility */
static _Atomic bool keep_running = ATOMIC_VAR_INIT(true);
/* Flag indicating the workload timed out (finite‑duration) */
static _Atomic bool timed_out = ATOMIC_VAR_INIT(false);
/* Process‑wide error indicator – non‑zero means an unrecoverable error occurred */
static _Atomic int program_error = ATOMIC_VAR_INIT(0);

/* -----------------------------------------------------------------
 * Helper: monotonic‑raw timestamp in nanoseconds
 * ----------------------------------------------------------------- */
static uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

/* -----------------------------------------------------------------
 * Write CSV header lines – called once after the log files are opened
 * ----------------------------------------------------------------- */
static void write_csv_headers(void)
{
    /* Application‑event log header */
    fprintf(app_log_fp,
            "timestamp_ns,record_type,requested_bytes,accepted_bytes,send_duration_ns,cumulative_accepted_bytes\n");
    fflush(app_log_fp);

    /* TCP_INFO snapshot log header */
    fprintf(tcpinfo_log_fp,
            "timestamp_ns,sample_duration_ns,tcpi_unacked,tcpi_sacked,tcpi_lost,tcpi_retrans,"\
            "tcpi_snd_cwnd,tcpi_ca_state,tcpi_snd_mss,tcpi_rtt,tcpi_notsent_bytes,"\
            "tcpi_pacing_rate,tcpi_delivery_rate\n");
    fflush(tcpinfo_log_fp);
}

/* -----------------------------------------------------------------
 * Sender thread – continuously handed data to the kernel.
 * Handles partial sends, records a single CSV line per iteration.
 * ----------------------------------------------------------------- */
static void *sender_thread(void *arg)
{
    (void)arg; /* unused */
    char *buf = malloc(SEND_BUF_SIZE);
    if (!buf) {
        perror("malloc");
        atomic_store(&keep_running, false);
        atomic_store(&program_error, 1);
        return NULL;
    }
    memset(buf, 'X', SEND_BUF_SIZE);

    uint64_t cumulative_sent = 0;
    while (atomic_load(&keep_running)) {
        /* Record start of a send attempt */
        uint64_t t_start = now_ns();
        if (fprintf(app_log_fp,
                    "%llu,pre_send,%zu,0,0,%llu\n",
                    (unsigned long long)t_start,
                    SEND_BUF_SIZE,
                    (unsigned long long)cumulative_sent) < 0) {
            perror("fprintf pre_send");
            atomic_store(&program_error, 1);
            atomic_store(&keep_running, false);
            break;
        }
        size_t remaining = SEND_BUF_SIZE;
        const char *p = buf;
        ssize_t accepted = 0;

        /* Loop until the whole buffer is handed to the kernel or an error occurs */
        while (remaining > 0 && atomic_load(&keep_running)) {
            ssize_t rc = send(sock_fd, p, remaining, MSG_NOSIGNAL);
            if (rc < 0) {
                if (errno == EINTR)
                    continue; /* retry */
                /* If this error occurs after we have signaled termination,
                 * it is expected (socket was shut down). */
                if (!atomic_load(&keep_running)) {
                    break; /* normal exit path */
                }
                perror("send");
                atomic_store(&program_error, 1);
                atomic_store(&keep_running, false);
                break;
            }
            if (rc == 0) {
                /* Should not happen on a blocking socket; treat as error */
                fprintf(stderr, "send returned 0 – socket closed?\n");
                if (!atomic_load(&keep_running)) {
                    break; /* normal exit path */
                }
                atomic_store(&program_error, 1);
                atomic_store(&keep_running, false);
                break;
            }
            p += rc;
            remaining -= rc;
            accepted += rc;
        }

        uint64_t t_end = now_ns();
        cumulative_sent += (uint64_t)accepted;

        /* Record completion of the send attempt */
        if (fprintf(app_log_fp,
                    "%llu,post_send,%zu,%zd,%llu,%llu\n",
                    (unsigned long long)t_end,
                    SEND_BUF_SIZE,
                    accepted,
                    (unsigned long long)(t_end - t_start),
                    (unsigned long long)cumulative_sent) < 0) {
            perror("fprintf post_send");
            atomic_store(&program_error, 1);
            atomic_store(&keep_running, false);
            break;
        }
    }

    free(buf);
    return NULL;
}

/* -----------------------------------------------------------------
 * Sampler thread – periodic TCP_INFO snapshots.
 * ONE CSV row per snapshot, INCLUDING the duration of the getsockopt()
 * call as sample_duration_ns.
 * ----------------------------------------------------------------- */
static void *sampler_thread(void *arg)
{
    (void)arg; /* unused */
    struct tcp_info ti;
    socklen_t ti_len = sizeof(ti);

    while (atomic_load(&keep_running)) {
        uint64_t t_start = now_ns();
        if (getsockopt(sock_fd, IPPROTO_TCP, TCP_INFO, &ti, &ti_len) < 0) {
            /* Expected if the socket has been shut down during termination */
            if (!atomic_load(&keep_running)) {
                break; /* normal exit */
            }
            perror("getsockopt(TCP_INFO)");
            atomic_store(&program_error, 1);
            atomic_store(&keep_running, false);
            break;
        }
        uint64_t t_end = now_ns();

        /* Some kernel versions lack tcpi_notsent_bytes, tcpi_pacing_rate
         * and tcpi_delivery_rate.  Use zero placeholders when the fields are
         * not present in struct tcp_info. */
        /* Verify kernel returned a struct large enough for the three optional fields */
        if (ti_len < offsetof(struct tcp_info, tcpi_delivery_rate) + sizeof(ti.tcpi_delivery_rate)) {
            fprintf(stderr, "getsockopt returned insufficient tcp_info size (%u bytes)\n", ti_len);
            atomic_store(&program_error, 1);
            atomic_store(&keep_running, false);
            break;
        }
        if (fprintf(tcpinfo_log_fp,
                    "%llu,%llu,%u,%u,%u,%u,%u,%u,%u,%u,%u,%llu,%llu\n",
                    (unsigned long long)t_start,
                    (unsigned long long)(t_end - t_start),
                    ti.tcpi_unacked,
                    ti.tcpi_sacked,
                    ti.tcpi_lost,
                    ti.tcpi_retrans,
                    ti.tcpi_snd_cwnd,
                    ti.tcpi_ca_state,
                    ti.tcpi_snd_mss,
                    ti.tcpi_rtt,
                    ti.tcpi_notsent_bytes,
                    ti.tcpi_pacing_rate,
                    ti.tcpi_delivery_rate) < 0) {
            perror("fprintf tcpinfo_log_fp");
            atomic_store(&program_error, 1);
            atomic_store(&keep_running, false);
            break;
        }

        /* Sleep for the remainder of the interval, compensating for work time */
        uint64_t now = now_ns();
        if (now < t_start + SAMPLE_INTERVAL_NS) {
            struct timespec ts;
            uint64_t delta = (t_start + SAMPLE_INTERVAL_NS) - now;
            ts.tv_sec = delta / 1000000000ull;
            ts.tv_nsec = delta % 1000000000ull;
            nanosleep(&ts, NULL);
        }
    }
    return NULL;
}

/* -----------------------------------------------------------------
 * Main – argument parsing, connection setup, thread launch, shutdown
 * ----------------------------------------------------------------- */
int main(int argc, char *argv[])
{
    int run_seconds = 0; /* 0 = infinite */
    if (argc > 1) {
        run_seconds = atoi(argv[1]);
        if (run_seconds < 0)
            run_seconds = 0;
    }

    /* Ignore SIGPIPE – send() will return -1/EPIPE instead of terminating */
    signal(SIGPIPE, SIG_IGN);

    /* Open CSV log files */
    app_log_fp = fopen("sender_app_log.csv", "w");
    tcpinfo_log_fp = fopen("sender_tcpinfo_log.csv", "w");
    if (!app_log_fp || !tcpinfo_log_fp) {
        perror("fopen");
        return EXIT_FAILURE;
    }

    /* Write CSV headers */
    write_csv_headers();

    /* Record monotonic‑raw / realtime mapping for later correlation */
    {
        struct timespec mono, real;
        if (clock_gettime(CLOCK_MONOTONIC_RAW, &mono) != 0 ||
            clock_gettime(CLOCK_REALTIME, &real) != 0) {
            perror("clock_gettime start mapping");
            atomic_store(&program_error, 1);
        } else {
            if (fprintf(app_log_fp,
                        "# monotonic_raw_start_ns=%llu, realtime_start_ns=%llu\n",
                        (unsigned long long)(mono.tv_sec * 1000000000ull + mono.tv_nsec),
                        (unsigned long long)(real.tv_sec * 1000000000ull + real.tv_nsec)) < 0) {
                perror("fprintf start mapping app_log_fp");
                atomic_store(&program_error, 1);
            }
            fflush(app_log_fp);
            if (fprintf(tcpinfo_log_fp,
                        "# monotonic_raw_start_ns=%llu, realtime_start_ns=%llu\n",
                        (unsigned long long)(mono.tv_sec * 1000000000ull + mono.tv_nsec),
                        (unsigned long long)(real.tv_sec * 1000000000ull + real.tv_nsec)) < 0) {
                perror("fprintf start mapping tcpinfo_log_fp");
                atomic_store(&program_error, 1);
            }
            fflush(tcpinfo_log_fp);
        }
    }

    /* -----------------------------------------------------------------
     * Create socket and connect to the receiver
     * ----------------------------------------------------------------- */
    sock_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (sock_fd < 0) {
        perror("socket");
        return EXIT_FAILURE;
    }
    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(REMOTE_PORT);
    if (inet_pton(AF_INET, REMOTE_ADDR, &addr.sin_addr) != 1) {
        fprintf(stderr, "Invalid address %s\n", REMOTE_ADDR);
        return EXIT_FAILURE;
    }
    if (connect(sock_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("connect");
        return EXIT_FAILURE;
    }

    /* ---------------------------------------------------------------
     * Launch the sender and sampler threads
     * --------------------------------------------------------------- */
    pthread_t th_sender, th_sampler;
    int rc;
    rc = pthread_create(&th_sender, NULL, sender_thread, NULL);
    if (rc != 0) {
        fprintf(stderr, "pthread_create sender: %s\n", strerror(rc));
        atomic_store(&program_error, 1);
        return EXIT_FAILURE;
    }
    rc = pthread_create(&th_sampler, NULL, sampler_thread, NULL);
    if (rc != 0) {
        fprintf(stderr, "pthread_create sampler: %s\n", strerror(rc));
        atomic_store(&keep_running, false);
        atomic_store(&program_error, 1);
        pthread_join(th_sender, NULL);
        return EXIT_FAILURE;
    }

    /* -----------------------------------------------------------------
     * Finite‑run handling – if a duration was supplied, sleep for that long
     * and then request termination.  If run_seconds == 0 we simply wait for
     * the threads (they run until an error occurs).
     * ----------------------------------------------------------------- */
    if (run_seconds > 0) {
        struct timespec ts = { .tv_sec = run_seconds, .tv_nsec = 0 };
        if (nanosleep(&ts, NULL) != 0) {
            perror("nanosleep");
            atomic_store(&program_error, 1);
        }
        /* Mark that we stopped due to timeout (i.e., aborted experiment) */
        atomic_store(&timed_out, true);
        atomic_store(&keep_running, false); /* signal threads to stop */
    }

    /* Interrupt any blocking I/O without closing the descriptor yet */
    if (sock_fd >= 0) {
        shutdown(sock_fd, SHUT_RDWR);
    }

    /* Wait for the worker threads to finish */
    pthread_join(th_sender, NULL);
    pthread_join(th_sampler, NULL);

    /* Now safe to close the socket */
    if (sock_fd >= 0) {
        close(sock_fd);
        sock_fd = -1;
    }
    /* Record end‑time clock mapping for post‑analysis */
    {
        struct timespec mono_end, real_end;
        if (clock_gettime(CLOCK_MONOTONIC_RAW, &mono_end) != 0 ||
            clock_gettime(CLOCK_REALTIME, &real_end) != 0) {
            perror("clock_gettime end mapping");
            atomic_store(&program_error, 1);
        } else {
            if (fprintf(app_log_fp,
                        "# monotonic_raw_end_ns=%llu, realtime_end_ns=%llu\n",
                        (unsigned long long)(mono_end.tv_sec * 1000000000ull + mono_end.tv_nsec),
                        (unsigned long long)(real_end.tv_sec * 1000000000ull + real_end.tv_nsec)) < 0) {
                perror("fprintf end mapping app_log_fp");
                atomic_store(&program_error, 1);
            }
            if (fprintf(tcpinfo_log_fp,
                        "# monotonic_raw_end_ns=%llu, realtime_end_ns=%llu\n",
                        (unsigned long long)(mono_end.tv_sec * 1000000000ull + mono_end.tv_nsec),
                        (unsigned long long)(real_end.tv_sec * 1000000000ull + real_end.tv_nsec)) < 0) {
                perror("fprintf end mapping tcpinfo_log_fp");
                atomic_store(&program_error, 1);
            }
        }
    }

    /* Record experiment status (normal completion, timeout‑abort, or error) */
    if (atomic_load(&program_error)) {
        fprintf(app_log_fp, "# experiment_status=error\n");
        fprintf(tcpinfo_log_fp, "# experiment_status=error\n");
    } else if (atomic_load(&timed_out)) {
        fprintf(app_log_fp, "# experiment_status=timeout_aborted\n");
        fprintf(tcpinfo_log_fp, "# experiment_status=timeout_aborted\n");
    } else {
        fprintf(app_log_fp, "# experiment_status=normal\n");
        fprintf(tcpinfo_log_fp, "# experiment_status=normal\n");
    }

    fclose(app_log_fp);
    fclose(tcpinfo_log_fp);

    /* Return failure if any thread reported an error */
    return (atomic_load(&program_error) != 0) ? EXIT_FAILURE : EXIT_SUCCESS;
}
