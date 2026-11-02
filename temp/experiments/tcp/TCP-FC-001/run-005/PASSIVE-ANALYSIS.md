# PASSIVE ANALYSIS of Run-005 (TCP-FC-001)

This document records the offline passive analysis performed on run‑005, which
applies a **single receiver‑side `SO_RCVBUF = 64 KiB`** intervention relative to
run‑004.

* **Receiver socket configuration**
  * Requested `SO_RCVBUF` = **65536** bytes
  * Reported (actual) buffer size = **131072** bytes (kernel doubled the value)
  * Pause on the receiver side began at **1791409208759270898 ns** after the
    connection was accepted and lasted **300 285 454 ns** (~0.300 s).

* **TCP window scaling**
  * Client (sender) window‑scale option = **7**
  * Server (receiver) window‑scale option = **1**

* **Advertised window trajectory (server → client ACKs)**
  * Initial advertised window (raw) = **39820** → scaled **79640** bytes
  * Minimum raw window observed = **0** (zero‑window) → scaled **0** bytes
    (non‑zero minimum = **9306** → scaled **18612** bytes)
  * First zero‑window packet at **1791409208853555000 ns**
  * Total zero‑window advertisements = **2**
  * Last zero‑window packet at **1791409209065246000 ns**
  * First positive window after the zero‑window episode at
    **1791409209072252000 ns** (raw **31796**, scaled **63592** bytes)

* **New‑data high‑water (sender) progress**
  * Highest sequence number observed in the capture: **133 989 237**
  * At the start of the zero‑window episode the receiver had ACKed up to
    **373 377** (high‑water ≈ 373 376 bytes).
  * After the window reopened the first new ACK advanced to **380 829**,
    providing **7 452 bytes** of additional unique data.

* **Passive receive credit reconstruction (RFC 9293)**
  * Minimum usable credit (reconstructed) = **0** bytes (credit closed)
  * Reconstruction‑gap count = **1**
  * Negative‑credit anomaly count = **2710** (many moments where the
    calculated credit would be negative due to off‑loading effects)

* **Phase assessment**
  * **Phase A** – sufficient credit and data progress – **SUFFICIENT**
  * **Phase B** – zero‑window credit with stationary high‑water *and* a
    blocking `send()` call that began before the credit closed and remained
    outstanding throughout the zero‑credit interval – **SUFFICIENT**
  * **Phase C** – window reopened and data progress resumed – **SUFFICIENT**

* **Loss / congestion context** – No retransmissions, duplicate ACKs, or ECN
  evidence were observed during the candidate Phase B interval.

* **Comparison with run‑004**
  * Run‑004 never observed a zero‑window; the minimum raw window was **397**
    bytes (scaled ≈ 508 16 bytes) and credit never closed.
  * The explicit `SO_RCVBUF` reduction in run‑005 introduced a zero‑window
    episode and the associated credit‑closure behaviour, confirming the
    intended effect of the intervention.

 * **Overall classification** – **A. VALID A->B->C PASSIVE FC TRANSITION**

---

## Forensic correction

The initial analysis mistakenly paired the *post_send* record with the *pre_send*
record that appears **after** it in the CSV file:

```
1791409209073288466,post_send,,65536,301846921,1245184
1791409209073309153,pre_send,65536,,,1245184
```

When the timestamps are examined, the `pre_send` event actually occurred **earlier**
at `1791409208771441545` (the correct preceding `pre_send` line).  The correct
pair is:

```
1791409208771441545,pre_send,65536,,,1179648
1791409209073288466,post_send,,65536,301846921,1245184
```

Using these timestamps the computed duration matches the recorded duration
(`301846921 ns`), and the `send()` call spans the entire zero‑window interval,
providing the required controlled evidence that the sender continued to
attempt to supply data while the receiver credit was zero.  The Phase B
assessment and overall classification have been updated accordingly.

The analysis file was generated without altering any raw experiment artifacts.