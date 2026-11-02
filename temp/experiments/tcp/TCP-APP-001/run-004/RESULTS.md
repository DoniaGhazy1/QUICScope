# TCP-APP-001 Run 004 – Results

---

## 1. Experiment configuration

* **VM 1 (sender / passive observer)**: `192.168.88.20` ens4
* **VM 2 (receiver)**: `192.168.88.21` ens4
* **TCP port**: `5202`
* **Application writes**: `20` writes
* **Bytes per write**: `65 536 bytes` (64 KiB)
* **Controlled application pause**: `100 ms` between writes
* **Expected total payload**: `1 310 720 bytes` (`20 × 65 536`)

Additional environment details (from `environment.txt`):

```
UTC date/time: 2026-10-07 18:37:03 UTC
Hostname: sriov-vm1
Kernel: 6.8.0-146-generic
ens4 IPv4: 192.168.88.20/24
ens4 link state: up
ens4 MTU: 1500
Route to 192.168.88.21:
192.168.88.21 dev ens4 src 192.168.88.20 uid 1000
    cache
TCP congestion control: cubic
Sender parameters:
  server = 192.168.88.21
  port = 5202
  chunk size = 65536
  pause = 0.100
  repetitions = 20
```

---

## 2. Sender results

* **Exit status**: `0`
* **Successful application writes**: `20`
* **Each `post_send` event** requested **65 536 bytes**
* **Each `post_send` event** accepted **65 536 bytes**
* **Total bytes accepted by sender**: **1 310 720 bytes**

---

## 3. Controlled‑workload timeline (`controlled_workload_timeline.log`)

| Event                | Count |
|----------------------|-------|
| `conn_established`   | 1 |
| `pre_send`           | 20 |
| `post_send`          | 20 |
| `app_sleep_start`    | 20 |
| `app_sleep_end`      | 20 |
| `close_start`        | 1 |
| `close_end`          | 1 |

* **Timeline file size**: **3 248 bytes**

> The timeline provides controlled application‑workload timing. It does **NOT** directly measure the transport‑layer `HasTransportPendingData` (D) state.

---

## 4. Receiver results (manually verified on VM 2)

The one‑shot receiver on VM 2 reported:

```
[INFO] Starting TCP-APP-001 receiver
[INFO] Listening on 0.0.0.0:5202
[INFO] Connection accepted from ('192.168.88.20', 59990)
[INFO] Total bytes received: 1310720
[INFO] Connection closed
```

* **Accepted connection** from `192.168.88.20:59990`
* **Total bytes received**: **1 310 720 bytes**
* **Connection closed** normally; the receiver stopped listening after the single workload execution.
* The **sender‑accepted total** (`1 310 720 bytes`) matches the **receiver‑received total** exactly.

---

## 5. Passive capture integrity

* **`tcp_capture.pcap` size**: **17 360 bytes**
* **tcpdump final statistics** (from `capture_stats.txt`):
  * `100 packets captured`
  * `100 packets received by filter`
  * `0 packets dropped by kernel`
* **Read‑validation** of the pcap (`tcpdump -nn -r …`) exited with status **0** and produced no "truncated dump file" warning.

Therefore:

**PASSIVE CAPTURE INTEGRITY: VALID**

---

## 6. Passive capture observations

* **Observed TCP 4‑tuple**: `192.168.88.20:59990 -> 192.168.88.21:5202`
* **SYN** packet – present
* **SYN/ACK** packet – present
* **Final handshake ACK** – present
* **Sender data** packets (`Flags [P.]`) – present (≈ 48 packets)
* **Reverse ACKs** (`Flags [.]` from the receiver) – present (≈ 48 packets)
* **FIN / connection termination** packets – present (2 packets)

Repeated data‑transmission bursts and intervening gaps are visible. Their timing is consistent with the repeated 64 KiB application writes and controlled 100 ms application pauses recorded in the workload timeline.

*Note*: Because the capture was performed on the sender host, packet segmentation may reflect GSO/TSO offload behavior. The observed segmentation therefore **must not** be interpreted as a one‑to‑one mapping to physical wire‑level packets.

---

## 7. Run validity

**WORKLOAD VALIDITY:** **VALID**

The controlled workload completed successfully end‑to‑end. The sender accepted **1 310 720 bytes** and the receiver received exactly **1 310 720 bytes** on the matching TCP connection.

**PASSIVE CAPTURE VALIDITY:** **VALID**

The capture completed cleanly, passed read‑integrity validation, and tcpdump reported `100` captured, `100` received by filter, and `0` dropped by kernel.

**OVERALL DISPOSITION:**

Run‑004 is the authoritative experimental run for subsequent passive‑observability analysis.

---

## 8. Interpretation boundaries

This document **does NOT** establish any of the following:

* `D = false`
* `APPLICATION_LIMITED`
* `F = true`
* `C = true`
* Exact transport‑layer send‑buffer emptiness
* Exact `bytes_in_flight`
* One‑to‑one mapping between application writes and captured packet bursts

The 100 ms pauses are **ground‑truth about the application behavior**, not exact ground‑truth for the transport‑level `HasTransportPendingData` state. Any later application‑limited classification must be derived separately by comparing the controlled‑workload timeline with the passive TCP evidence and by explicitly stating which observations are direct, derived, or inferred.

---

## 9. Artifact inventory

Preserved artifacts for run‑004:

* `environment.txt`
* `sender.log`
* `sender_exit.txt`
* `controlled_workload_timeline.log`
* `tcp_capture.pcap`
* `capture_stats.txt`
* `tcpdump_pid.txt`
* `RESULTS.md`
