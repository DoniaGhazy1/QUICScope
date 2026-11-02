/*
 * TCP-CC-001 receiver implementation
 * ------------------------------------------------------------
 * Listens on port 5204, accepts a single connection and continuously
 * receives data, discarding the payload.  The program records the
 * cumulative number of bytes received and timestamps the updates –
 * this is optional but useful for later sanity checks.
 */

#define _GNU_SOURCE

/*
 * TCP-CC-001 receiver (revised)
 * ------------------------------------------------------------
 * Listens on TCP port 5204, accepts a single connection, and reads the
 * incoming stream continuously, discarding the payload.  It records a
 * CSV log that contains a header row and event rows with monotonic
 * timestamps.  The log reports connection establishment, periodic byte
 * counters, EOF, errors and the final total.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <time.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

static const int LISTEN_PORT = 5204;
static const size_t RECV_BUF_SIZE = 64 * 1024; /* 64 KB */

/* Helper: monotonic‑raw timestamp in nanoseconds */
static uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

int main(void)
{
    int listen_fd = -1, client_fd = -1;
    struct sockaddr_in addr;
    FILE *log_fp = NULL;
    char *buf = NULL;
    uint64_t total_recv = 0;

    /* Open CSV log file */
    log_fp = fopen("receiver_log.csv", "w");
    if (!log_fp) {
        perror("fopen");
        return EXIT_FAILURE;
    }

    /* Write CSV header */
    fprintf(log_fp,
            "timestamp_ns,event,total_received_bytes\n");
    fflush(log_fp);

    listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd < 0) {
        perror("socket");
        fclose(log_fp);
        return EXIT_FAILURE;
    }

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(LISTEN_PORT);
    if (bind(listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(listen_fd);
        fclose(log_fp);
        return EXIT_FAILURE;
    }
    if (listen(listen_fd, 1) < 0) {
        perror("listen");
        close(listen_fd);
        fclose(log_fp);
        return EXIT_FAILURE;
    }

    fprintf(stderr, "Receiver listening on port %d…\n", LISTEN_PORT);
    client_fd = accept(listen_fd, NULL, NULL);
    if (client_fd < 0) {
        perror("accept");
        close(listen_fd);
        fclose(log_fp);
        return EXIT_FAILURE;
    }
    close(listen_fd);
    fprintf(stderr, "Connection accepted – receiving data...\n");
    fprintf(log_fp, "%llu,connected,0\n",
            (unsigned long long)now_ns());
    fflush(log_fp);

    buf = malloc(RECV_BUF_SIZE);
    if (!buf) {
        perror("malloc");
        close(client_fd);
        fclose(log_fp);
        return EXIT_FAILURE;
    }

    while (1) {
        ssize_t rc = recv(client_fd, buf, RECV_BUF_SIZE, 0);
        if (rc < 0) {
            if (errno == EINTR)
                continue;
            perror("recv");
            fprintf(log_fp, "%llu,error,0\n",
                    (unsigned long long)now_ns());
            break;
        }
        if (rc == 0) {
            /* Peer closed – normal EOF */
            fprintf(stderr, "Peer closed the connection.\n");
            fprintf(log_fp, "%llu,eof,0\n",
                    (unsigned long long)now_ns());
            break;
        }
        total_recv += (uint64_t)rc;
        /* Log every 10 MiB to keep the file size reasonable */
        if (total_recv % (10ULL * 1024 * 1024) < (uint64_t)rc) {
            fprintf(log_fp, "%llu,progress,%llu\n",
                    (unsigned long long)now_ns(),
                    (unsigned long long)total_recv);
            fflush(log_fp);
        }
    }

    /* Final summary line */
    fprintf(log_fp, "%llu,final,%llu\n",
            (unsigned long long)now_ns(),
            (unsigned long long)total_recv);
    fflush(log_fp);

    free(buf);
    close(client_fd);
    fclose(log_fp);
    return EXIT_SUCCESS;
}
