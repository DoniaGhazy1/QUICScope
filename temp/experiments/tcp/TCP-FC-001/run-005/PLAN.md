# RUN-005 PLAN – TCP‑FC‑001

## Single experimental intervention (relative to run‑004)

*The receiver socket’s receive buffer is explicitly bounded to **64 KiB** by
setting `SO_RCVBUF` on the listening socket **before** `listen()`.  Setting this
option disables per‑socket automatic receive‑buffer tuning, providing a fixed,
controlled buffer configuration for the connection.*

```python
REQUESTED_RCVBUF = 64 * 1024   # 64 KiB

listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listen_sock.setsockopt(socket.SOL_SOCKET,
                       socket.SO_RCVBUF,
                       REQUESTED_RCVBUF)
listen_sock.bind((LISTEN_ADDR, LISTEN_PORT))
listen_sock.listen(1)
```

After the connection is accepted, the program logs both the requested and the
kernel‑reported buffer size:

```python
log.writerow([time.time_ns(), "rcvbuf_requested", REQUESTED_RCVBUF, ""])
actual_rcvbuf = conn.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
log.writerow([time.time_ns(), "rcvbuf_reported", actual_rcvbuf, ""])
```

All other experiment parameters remain **identical** to run‑004:

* `NORMAL_READ_BYTES = 256 KiB`
* `PAUSE_SEC = 0.300 s`
* Sender payload size = 64 KiB, total = 128 MiB, continuous writes, no sleeps
* Capture buffer `tcpdump -B 32768`
* MTU = 1500, TCP CC = cubic, offloads unchanged, sysctls untouched

**Important clarification:** The advertised TCP receive window observed in the
pcap is the authoritative evidence for whether receiver credit reaches zero.
It is **not** assumed to equal either the *requested* (`REQUESTED_RCVBUF`) or the
*reported* (`getsockopt`) `SO_RCVBUF` values.  The latter reflect kernel‑internal
buffer allocation (typically ≈ 2× the request) and the socket option does not
directly map to the on‑wire Window field.

---

*Document version: 1.0 – 2026‑10‑07*
