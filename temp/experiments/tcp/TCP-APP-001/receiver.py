#!/usr/bin/env python3

"""TCP receiver for experiment TCP-APP-001.

Listens on all interfaces (0.0.0.0) port 5202, accepts a single incoming
connection, and reads data as fast as possible without artificial throttling.
It reports key events to stdout and counts the total number of bytes received.
The experiment expects a total payload of 64 KiB × 20 = 1,310,720 bytes.
"""

import socket
import sys
import time
from pathlib import Path

LISTEN_ADDR = "0.0.0.0"
PORT = 5202
RECV_BUFFER = 64 * 1024  # 64 KiB receive buffer per ``recv`` call


def main() -> None:
    print("[INFO] Starting TCP-APP-001 receiver", flush=True)
    try:
        srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv_sock.bind((LISTEN_ADDR, PORT))
        srv_sock.listen(1)
        print(f"[INFO] Listening on {LISTEN_ADDR}:{PORT}", flush=True)
        conn, addr = srv_sock.accept()
        print(f"[INFO] Connection accepted from {addr}", flush=True)
        # Record acceptance timestamp (optional – not written to a file per spec)
        _ = time.time_ns()

        total_bytes = 0
        while True:
            data = conn.recv(RECV_BUFFER)
            if not data:
                break
            total_bytes += len(data)
        print(f"[INFO] Total bytes received: {total_bytes}", flush=True)

        # Record close timestamp (optional – not written to a file per spec)
        _ = time.time_ns()
        conn.close()
        srv_sock.close()
        print("[INFO] Connection closed", flush=True)
    except Exception as exc:
        print(f"[ERROR] Receiver encountered an exception: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
