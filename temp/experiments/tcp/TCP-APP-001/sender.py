#!/usr/bin/env python3

"""TCP sender for experiment TCP-APP-001.

The script connects to the receiver at 192.168.88.21:5202, sends a fixed-size
application payload (64 KiB) repeatedly, and inserts a 100 ms idle interval
between bursts.  All significant events are logged to
``controlled_workload_timeline.log`` in CSV format using ``time.time_ns()`` for
timestamping so that the log can be aligned with a ``tcpdump`` capture that
records wall‑clock timestamps.

The script deliberately handles partial ``send()`` returns – it loops until the
entire 64 KiB chunk has been accepted by the socket.  Exception handling ensures
clean shutdown of the connection on error.
"""

import socket
import time
import os
import struct
import sys
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration constants (per the experiment specification)
# ---------------------------------------------------------------------------
SERVER = "192.168.88.21"
PORT = 5202  # dedicated experiment port
CHUNK_SIZE = 64 * 1024  # 64 KiB
PAUSE_SEC = 0.100  # 100 ms
REPETITIONS = 20

# The timeline log path will be supplied via a required ``--timeline`` argument.
# A placeholder is defined for type checking; it will be set after argument parsing.
LOG_PATH: Path = None  # will be set at runtime after parsing args


def _write_log(event: str, ts_ns: int, iteration: str = "", bytes_req: str = "", bytes_acc: str = "") -> None:
    """Write a single CSV line to the timeline log.

    The CSV columns are:
        event, ts_ns, iteration, bytes_requested, bytes_accepted
    Empty strings are written for fields that are not applicable.
    """
    line = f"{event},{ts_ns},{iteration},{bytes_req},{bytes_acc}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        # In case logging fails we still want the script to exit cleanly.
        print(f"[ERROR] Failed to write log: {exc}", file=sys.stderr)


def main() -> None:
    # ---------------------------------------------------------------------
    # Argument parsing – obtain timeline file path
    # ---------------------------------------------------------------------
    parser = argparse.ArgumentParser(description="TCP-APP-001 sender")
    parser.add_argument(
        "--timeline",
        required=True,
        help="Path to the controlled workload timeline log file",
    )
    args = parser.parse_args()

    timeline_path = Path(args.timeline).expanduser().resolve()
    if timeline_path.exists():
        print(
            f"[ERROR] Timeline file {timeline_path} already exists. Refusing to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)
    # Ensure parent directory exists.
    timeline_path.parent.mkdir(parents=True, exist_ok=True)

    global LOG_PATH
    LOG_PATH = timeline_path

    print("[INFO] Starting TCP-APP-001 sender", flush=True)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SERVER, PORT))
        _write_log("conn_established", time.time_ns())
        print(f"[INFO] Connected to {SERVER}:{PORT}", flush=True)

        payload = b"x" * CHUNK_SIZE
        for i in range(REPETITIONS):
            # Pre‑send event
            _write_log("pre_send", time.time_ns(), str(i))

            # Send the full chunk, handling partial sends.
            total_sent = 0
            while total_sent < CHUNK_SIZE:
                try:
                    sent = sock.send(payload[total_sent:])
                except OSError as e:
                    print(f"[ERROR] send() failed on iteration {i}: {e}", file=sys.stderr)
                    raise
                if sent == 0:
                    raise RuntimeError("socket connection broken during send")
                total_sent += sent

            # Post‑send event – record the number of bytes accepted.
            _write_log("post_send", time.time_ns(), str(i), str(CHUNK_SIZE), str(total_sent))
            print(f"[INFO] Sent chunk {i+1}/{REPETITIONS} ({total_sent} bytes)", flush=True)

            # Sleep interval
            _write_log("app_sleep_start", time.time_ns(), str(i))
            time.sleep(PAUSE_SEC)
            _write_log("app_sleep_end", time.time_ns(), str(i))

        # Graceful shutdown of the write side.
        _write_log("close_start", time.time_ns())
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            # The socket may already be closed; ignore.
            pass
        sock.close()
        _write_log("close_end", time.time_ns())
        print("[INFO] Connection closed cleanly", flush=True)

    except Exception as exc:
        print(f"[ERROR] Sender encountered an exception: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
