# RUN-005 – RAW EXECUTION SUMMARY

## 1. Sender execution
- **Exit status:** 0
- **Accepted‑byte total:** 134217728 bytes
- **Event counts:**
  - conn_established: 1
  - send_start: 1
  - pre_send: 2048
  - post_send: 2048
  - send_end: 1
  - close_start: 1
  - close_end: 1
- **Maximum `send()` duration:** 301846921 ns

## 2. Connection details
Four‑tuple: 192.168.88.20:36040 → 192.168.88.21:5203

## 3. Capture statistics
- **Capture file size:** 134683326 bytes
- **Packets captured:** 8431
- **Packets received by filter:** 8449
- **Packets dropped by kernel:** 0
- **SYN:** present
- **SYN‑ACK:** present
- **Data:** present
- **Receiver ACK/window:** present
- **FIN:** absent
- **RST:** absent

## 4. Execution anomalies
None observed.

## 5. Run‑005 changes
Run‑005 changes only the receiver per‑socket receive‑buffer configuration relative to run‑004.

Requested receiver `SO_RCVBUF`: 65536 bytes.

**SEMANTIC ANALYSIS:** NOT YET PERFORMED
**TCP-FC-001 STATUS:** NOT FROZEN
