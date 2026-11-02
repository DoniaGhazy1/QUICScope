#!/usr/bin/env python3
"""TCP-FC-001 sender application.

The sender continuously offers data to the receiver at 192.168.88.21:5203 using a
blocking TCP socket.  It logs a CSV timeline of its activity with nanosecond
resolution timestamps.

Events logged (columns: timestamp_ns,event,requested_bytes,accepted_bytes,
duration_ns,cumulative_bytes):
    conn_established, send_start, pre_send, post_send, send_end,
    close_start, close_end, error

The implementation does **not** use ``socket.sendall`` because we want to expose
individual ``send`` calls and their blocking duration.
"""

import socket
import time
import csv
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEST_IP = "192.168.88.21"
DEST_PORT = 5203

# Fixed payload size for each send request (64 KiB).
PAYLOAD_SIZE = 64 * 1024  # 65536 bytes

# Total number of bytes to transmit before gracefully closing the connection.
# A value of 128 MiB is chosen to guarantee that the sender remains active
# throughout the receiver's normal‑read phase (~2 s), the receiver pause (~0.3 s),
# and the resume phase without being excessively large (≈10 s of transmission at
# 100 Mbit/s).
TOTAL_BYTES = 128 * 1024 * 1024  # 134,217,728 bytes

# ---------------------------------------------------------------------------
# Helper for CSV logging.  All rows have six columns; unused columns are left
# empty to keep the format consistent.
# ---------------------------------------------------------------------------
def csv_writer():
    writer = csv.writer(sys.stdout)
    # Optional header row for readability (ignored by downstream parsing if not
    # expected).
    writer.writerow([
        "timestamp_ns",
        "event",
        "requested_bytes",
        "accepted_bytes",
        "duration_ns",
        "cumulative_bytes",
    ])
    return writer


def main() -> None:
    cumulative = 0
    log = csv_writer()

    # --------------------------------------------------------------------
    # Connection setup
    # --------------------------------------------------------------------
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((DEST_IP, DEST_PORT))
    except Exception as exc:  # pragma: no cover – defensive; will be caught by static analysis
        log.writerow([time.time_ns(), "error", "", "", "", ""])
        raise

    log.writerow([time.time_ns(), "conn_established", "", "", "", cumulative])

    # --------------------------------------------------------------------
    # Data transmission phase
    # --------------------------------------------------------------------
    log.writerow([time.time_ns(), "send_start", "", "", "", cumulative])

    # Reusable payload – contents are not material for the experiment.
    payload = b"\x00" * PAYLOAD_SIZE

    while cumulative < TOTAL_BYTES:
        # Determine the target size for this iteration.  It may be smaller than
        # PAYLOAD_SIZE for the final chunk.
        remaining = TOTAL_BYTES - cumulative
        requested = PAYLOAD_SIZE if remaining >= PAYLOAD_SIZE else remaining

        # Record the moment just before issuing the blocking send.
        pre_ts = time.time_ns()
        log.writerow([pre_ts, "pre_send", requested, "", "", cumulative])

        try:
            # ``socket.send`` may return fewer bytes than requested; the loop
            # will continue until the total byte budget is satisfied.
            sent = sock.send(payload[:requested])
        except Exception as exc:  # pragma: no cover – defensive
            log.writerow([time.time_ns(), "error", requested, "", "", cumulative])
            break

        post_ts = time.time_ns()
        duration = post_ts - pre_ts
        cumulative += sent

        log.writerow([
            post_ts,
            "post_send",
            "",
            sent,
            duration,
            cumulative,
        ])

        # ``sent`` may be zero only on a closed socket; break to avoid infinite
        # looping.
        if sent == 0:
            break

    log.writerow([time.time_ns(), "send_end", "", "", "", cumulative])

    # --------------------------------------------------------------------
    # Graceful shutdown
    # --------------------------------------------------------------------
    log.writerow([time.time_ns(), "close_start", "", "", "", cumulative])
    try:
        sock.shutdown(socket.SHUT_WR)
    except Exception:
        # The peer may have already closed; ignore.
        pass
    sock.close()
    log.writerow([time.time_ns(), "close_end", "", "", "", cumulative])


if __name__ == "__main__":
    main()
