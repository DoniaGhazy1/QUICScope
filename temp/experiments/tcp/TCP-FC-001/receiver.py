#!/usr/bin/env python3
"""TCP-FC-001 receiver application.

The receiver listens on 0.0.0.0:5203 and performs a deterministic sequence of
phases to create a controlled pause in its reading of incoming data.  It logs a
CSV timeline using nanosecond timestamps.

Logged columns: timestamp_ns,event,bytes_read,cumulative_bytes

Events:
    conn_accepted
    normal_read_start
    read_progress
    recv_pause_start
    recv_pause_end
    resume_read_start
    resume_read_progress
    peer_closed
    close
"""

import socket
import time
import csv
import sys

# ---------------------------------------------------------------------------
# Configuration (constants are chosen to match the experiment description).
# ---------------------------------------------------------------------------
LISTEN_ADDR = "0.0.0.0"
LISTEN_PORT = 5203

# Normal read phase: read until this many bytes have been received.  Using a
# deterministic byte count ensures the pause will be entered regardless of the
# underlying link speed.  eight‑MiB (8 MiB) matches the experiment design.
# Normal read phase: read until this many bytes have been received.  The
# threshold is reduced from eight MiB (8 MiB) to **256 KiB** for run‑002 to
# cause the receiver’s advertised window to exhaust earlier while leaving a
# substantial amount of unsent payload on the sender side.
NORMAL_READ_BYTES = 256 * 1024

# Receiver pause duration (seconds).  This is the controlled pause that
# intentionally stops consuming data.
PAUSE_SEC = 0.300

# Size of each ``recv`` call.  64 KiB mirrors the sender's payload size but is not
# required to match exactly.
RECV_BUF_SIZE = 64 * 1024

# ---------------------------------------------------------------------------
# New: explicit receive‑buffer size (64 KiB) – disables per‑socket autotuning.
# ---------------------------------------------------------------------------
REQUESTED_RCVBUF = 64 * 1024


def csv_writer():
    writer = csv.writer(sys.stdout)
    writer.writerow([
        "timestamp_ns",
        "event",
        "bytes_read",
        "cumulative_bytes",
    ])
    return writer


def main() -> None:
    log = csv_writer()
    cumulative = 0

    # --------------------------------------------------------------------
    # Socket setup and accept
    # --------------------------------------------------------------------
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Set the receive buffer before the socket begins listening – this fixes
    # the buffer size for the accepted connection and disables automatic
    # receive‑buffer tuning for that socket.
    listen_sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_RCVBUF,
        REQUESTED_RCVBUF,
    )
    listen_sock.bind((LISTEN_ADDR, LISTEN_PORT))
    listen_sock.listen(1)

    conn, addr = listen_sock.accept()
    log.writerow([time.time_ns(), "conn_accepted", "", ""])
    # Log the requested receive‑buffer size (conceptual) and the actual kernel
    # allocation reported by getsockopt.  Neither value is taken as the TCP
    # advertised window; that is observed in the capture.
    log.writerow([time.time_ns(), "rcvbuf_requested", REQUESTED_RCVBUF, ""])
    actual_rcvbuf = conn.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    log.writerow([time.time_ns(), "rcvbuf_reported", actual_rcvbuf, ""])

    # --------------------------------------------------------------------
    # Normal read phase (no artificial delay)
    # --------------------------------------------------------------------
    log.writerow([time.time_ns(), "normal_read_start", "", ""])
    # Normal read phase – continue reading until the cumulative byte count
    # reaches the configured threshold.
    while cumulative < NORMAL_READ_BYTES:
        data = conn.recv(RECV_BUF_SIZE)
        if not data:
            # Peer closed early – record and break.
            log.writerow([time.time_ns(), "peer_closed", "", cumulative])
            conn.close()
            log.writerow([time.time_ns(), "close", "", cumulative])
            return
        bytes_read = len(data)
        cumulative += bytes_read
        log.writerow([time.time_ns(), "read_progress", bytes_read, cumulative])

    # --------------------------------------------------------------------
    # Receiver pause – intentionally stop reading data.
    # --------------------------------------------------------------------
    log.writerow([time.time_ns(), "recv_pause_start", "", cumulative])
    time.sleep(PAUSE_SEC)
    log.writerow([time.time_ns(), "recv_pause_end", "", cumulative])

    # --------------------------------------------------------------------
    # Resume reading until the peer closes the connection.
    # --------------------------------------------------------------------
    log.writerow([time.time_ns(), "resume_read_start", "", cumulative])
    while True:
        data = conn.recv(RECV_BUF_SIZE)
        if not data:
            log.writerow([time.time_ns(), "peer_closed", "", cumulative])
            break
        bytes_read = len(data)
        cumulative += bytes_read
        log.writerow([time.time_ns(), "resume_read_progress", bytes_read, cumulative])

    # --------------------------------------------------------------------
    # Clean termination
    # --------------------------------------------------------------------
    conn.close()
    log.writerow([time.time_ns(), "close", "", cumulative])


if __name__ == "__main__":
    main()
