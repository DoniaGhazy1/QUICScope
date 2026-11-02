# RUN‑004 – RAW EXECUTION SUMMARY

**Purpose**: Valid measurement‑quality repeat of run‑002 with the same TCP
workload and a larger tcpdump capture buffer (`-B 32768`).

---

## 1. Sender execution

| Item | Value |
|------|-------|
| **Exit status** | `0` |
| **Accepted‑byte total** | `134 217 728 bytes` (exact payload) |
| **Event counts** |
| &nbsp;&nbsp;`conn_established` | 1 |
| &nbsp;&nbsp;`send_start` | 1 |
| &nbsp;&nbsp;`pre_send` | 2048 |
| &nbsp;&nbsp;`post_send` | 2048 |
| &nbsp;&nbsp;`send_end` | 1 |
| &nbsp;&nbsp;`close_start` | 1 |
| &nbsp;&nbsp;`close_end` | 1 |
| **Maximum `send()` duration** | `110 481 055 ns` (~110 ms) |

## 2. Connection details (identified from capture)

*Four‑tuple*: `192.168.88.20:35006 → 192.168.88.21:5203`

## 3. Capture statistics

| Metric | Value |
|--------|-------|
| **Capture file size** | `134 630 972 bytes` |
| **Packets captured** | `4014` |
| **Packets received by filter** | `4014` |
| **Packets dropped by kernel** | `0` |

### Packet‑type presence for the identified flow

| Packet type | Present? | Count |
|------------|----------|-------|
| SYN | Yes | `1` |
| SYN‑ACK | Yes | `1` |
| Data (payload) | Yes | `2503` |
| Receiver ACK (no payload) | Yes | `1492` |
| FIN | Yes (`[FP.]`) | `1` |
| RST | No | `0` |

## 4. Execution anomalies

* No errors were written to `sender_stderr.txt`.
* The capture shows a clean handshake, full data transfer, and a proper FIN.

## 5. Validation outcome

All required validity criteria are satisfied:
* Sender exit status = **0**
* Accepted‑byte total = **134 217 728** (the full payload)
* The four‑tuple is clearly identifiable in the capture.

Thus the run is **VALID**.

---

*Document version: 1.0 – 2026‑10‑07*

**SEMANTIC ANALYSIS:** NOT YET PERFORMED
**TCP‑FC‑001 STATUS:** NOT FROZEN
