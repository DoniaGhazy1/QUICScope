# PASSIVE ANALYSIS – TCP‑FC‑001 run‑004

**Purpose**: Offline analysis of the clean measurement‑quality repeat (run‑004) to
determine whether the receiver‑flow‑control transition (Phase A → B → C)
is observable.

---

## 1. TCP negotiation parameters

| Parameter | Value | Evidence level |
|-----------|-------|----------------|
| Client MSS | **1460 bytes** | **WIRE_DIRECT** (SYN options) |
| Server MSS | **1460 bytes** | **WIRE_DIRECT** (SYN‑ACK options) |
| Client window‑scale | **7** | **WIRE_DIRECT** (SYN options) |
| Server window‑scale | **7** | **WIRE_DIRECT** (SYN‑ACK options) |

## 2. New‑data progress (client → server)

The `sender_timeline.csv` shows a monotonic increase of the cumulative byte
counter from `0` to the full payload **134 217 728 bytes**.  The highest observed
`post_send` duration is **110 481 055 ns** (≈ 110 ms).

## 3. Receiver window timeline (server → client)

The capture contains **no zero‑window advertisements**.  The smallest raw
advertised window observed on the server side is **397 bytes** (raw) – after the
window‑scale factor of **7** this corresponds to **50 816 bytes** of usable
receive credit.

* First positive advertised window (SYN‑ACK) – raw **65160**, scaled →
  `65160 × 2^7 = 8 340 480 bytes`.
* Minimum positive advertised window – raw **397** (≈ 50 816 bytes after scaling).
* Zero‑window advertisements – **0** observed.

## 4. RFC‑9293 passive credit reconstruction

Using the RFC‑9293 update rule, the reconstructed credit never fell below the
minimum usable credit of **≈ 50 kB**.  Consequently:

* **Reconstruction‑gap count** – **0** (no ACK > observed client `snd_nxt`).
* **Negative‑credit anomalies** – **0**.
* **Minimum reconstructed credit** – **≈ 50 816 bytes** (> 0).

## 5. Phase classification

| Phase | Verdict | Reason |
|-------|---------|--------|
| A | **SUFFICIENT** | Credit > 0 and client `snd_nxt` increased continuously before any zero‑window (none). |
| B | **INSUFFICIENT** | No zero‑window / zero‑credit episode was observed; therefore the required stationary‑high‑water interval cannot be demonstrated. |
| C | **INSUFFICIENT** | Without a preceding zero‑window episode, a “re‑open” cannot be identified. |

## 6. Loss / congestion evidence during Phase B

Since Phase B is absent, there is **no passive evidence** of retransmissions,
duplicate‑ACK bursts, or ECN marks.

## 7. Comparison with run‑002

| Metric | run‑002 | run‑004 |
|--------|--------|--------|
| Kernel drops | **228** | **0** |
| Reconstruction gaps | **27** | **0** |
| Phase A | sufficient | sufficient |
| Phase B | insufficient (only 1 zero‑window) | insufficient (no zero‑window) |
| Phase C | sufficient | insufficient (no re‑open) |

The clean capture removes the ambiguity caused by packet loss in run‑002, but
the experiment still does not exhibit a zero‑window episode, so Phase B and C
remain unvalidated.

---

*Document version: 1.0 – 2026‑10‑07*
