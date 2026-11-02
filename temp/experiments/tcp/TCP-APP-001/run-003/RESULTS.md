# TCP‑APP‑001 Run 003 – Results

---

## 1. Experiment configuration

* **VM 1 (sender / observer)**: 192.168.88.20 ens4
* **VM 2 (receiver)**: 192.168.88.21 ens4
* **TCP port**: 5202
* **Application writes**: 20 writes
* **Bytes per write**: 65 536 bytes (64 KiB)
* **Controlled application pause**: 100 ms between writes
* **Expected total payload**: 1 310 720 bytes (20 × 65 536)

---

## 2. Sender results

* **Exit status**: `0`
* **Successful writes**: 20
* **Each `post_send` event** requested **65 536 bytes**
* **Each `post_send` event** accepted **65 536 bytes**
* **Total bytes accepted by sender**: **1 310 720 bytes**

---

## 3. Controlled‑workload timeline (`controlled_workload_timeline.log`)

| Event | Count |
|-------|-------|
| `conn_established` | 1 |
| `pre_send` | 20 |
| `post_send` | 20 |
| `app_sleep_start` | 20 |
| `app_sleep_end` | 20 |
| `close_start` | 1 |
| `close_end` | 1 |

* **Timeline file size**: **3 248 bytes**

---

## 4. Receiver results (manually verified on VM 2)

```
[INFO] Starting TCP-APP-001 receiver
[INFO] Listening on 0.0.0.0:5202
[INFO] Connection accepted from ('192.168.88.20', 39842)
[INFO] Total bytes received: 1310720
[INFO] Connection closed
```

* **Accepted connection** from `192.168.88.20:39842`
* **Total bytes received**: **1 310 720 bytes**
* **Connection closed** normally
* **Sender‑accepted‑byte total** matches the receiver byte total exactly.

---

## 5. Passive capture observations

* **Observed TCP 4‑tuple**: `192.168.88.20:39842 -> 192.168.88.21:5202`
* **SYN** packet observed (client → server)
* **SYN/ACK** packet observed (server → client)
* **Final handshake ACK** observed (client → server)
* **Sender data packets** observed (client → server, `Flags [P.]`)
* **Reverse ACKs** observed (server → client, `Flags [.]`)
 * **Repeated data‑transmission bursts** are visible. Their timing is consistent with the repeated 64 KiB application writes recorded in the controlled‑workload timeline.
 * **Intervening data‑transmission gaps** are visible, with timing roughly consistent with the controlled 100 ms application pauses.
* **No claim is made** that these gaps establish any transport‑level state (e.g., `D = false`).

---

## 6. Capture integrity problem

* **`tcp_capture.pcap` size**: **16 384 bytes**
* **Approximately 92 packet records** were readable from the capture.
* Reading the pcap produced the warning:
  
  `tcpdump: pcap_loop: truncated dump file; tried to read 66 captured bytes, only got 44`
* **Final FIN/connection‑termination packets** were **not available** in the readable capture (the pcap was truncated before they could be recorded).
* **`capture_stats.txt`** does **not** contain final captured/received/dropped statistics – it only shows the initial "listening on …" line.
* **Packet‑drop count is therefore UNKNOWN**; we do not report zero drops.

---

## 7. Run validity

**WORKLOAD VALIDITY:** **VALID**

The controlled application workload completed successfully end‑to‑end. VM 1’s sender accepted **1 310 720 bytes** from the application and VM 2’s receiver received exactly **1 310 720 bytes** on the matching TCP connection.

**PASSIVE CAPTURE VALIDITY:** **INVALID FOR SEMANTIC ANALYSIS**

The pcap is truncated and final capture statistics are unavailable. Therefore this run must **not** be used as the authoritative passive packet trace for evaluating TCP observability or for any application‑limited inference.

**OVERALL DISPOSITION:**

Run‑003 is preserved as evidence of a successful controlled workload with a **failed capture**. A new run should be performed (e.g., run‑004) to obtain a valid passive capture.

---

## 8. Interpretation boundaries

The following items are **explicitly NOT** inferred or claimed in this document:

* Classification of `D = false` or any transport‑level state.
* Classification of `APPLICATION_LIMITED`.
* Inference that the 100 ms pauses constitute exact transport‑level application‑limited intervals.
* Assumption of zero packet drops.
* Use of the truncated pcap as an authoritative source for semantic analysis.

The controlled application pauses are **ground‑truth about the application workload only**, not about the transport‑layer pending‑data state.
