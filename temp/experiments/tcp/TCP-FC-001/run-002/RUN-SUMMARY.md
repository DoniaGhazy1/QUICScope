# RUN‑SUMMARY – TCP‑FC‑001 run‑002

**Execution timestamp (UTC)**: Wed Oct  7 21:01:26 UTC 2026

## Intervention

Receiver pauses `recv()` after approximately **256 KiB** of data has been
consumed, sleeping for **300 ms** (`PAUSE_SEC = 0.300`). All other parameters are
identical to run‑001.

## Sender workload

* Total payload: **128 MiB** (`TOTAL_BYTES = 128 * 1024 * 1024`).
* Write size: **64 KiB** per `send()` (`PAYLOAD_SIZE = 64 * 1024`).
* Continuous writes – no artificial sleeps.

## Results

* **Sender exit status:** `0`
* **Sender accepted‑byte total:** `134217728`
* **Maximum `send()` duration:** `81890241` ns (`≈81.9 ms`)
* **Observed four‑tuple:** `192.168.88.20:40152 → 192.168.88.21:5203`
* **Capture file size:** `124840710` bytes
* **Tcpdump statistics** (from `tcpdump.log`):
  * Packets captured: `3751`
  * Packets received by filter: `3979`
  * Packets dropped by kernel: `228`
* **TCP structural observations**:
  * SYN present – yes
  * SYN‑ACK present – yes
  * Data packets present – yes
  * Receiver ACK / window advertisements present – yes
  * FIN present – no
  * RST present – no

## Execution anomalies

None detected.

---

SEMANTIC ANALYSIS: NOT YET PERFORMED
TCP-FC-001 STATUS: NOT FROZEN

*Document version: 1.0 – 2026‑10‑07*