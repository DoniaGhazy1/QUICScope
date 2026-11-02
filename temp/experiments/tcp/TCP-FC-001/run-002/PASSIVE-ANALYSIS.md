# Passive Analysis of TCP‑FC‑001 run‑002

## Summary table

| Evidence | Result | Evidence level | Limitation |
|----------|--------|----------------|------------|
| Negotiated server window‑scale (from SYN‑ACK) | **7** | **WIRE_DIRECT** (options field) | None |
| First zero‑window advertisement (receiver → sender) | 2026‑10‑07 21:00:51.949052 | **WIRE_DIRECT** (raw Window = 0) | Single packet observed – capture may have missed others |
| Number of zero‑window ads observed | **1** | **WIRE_DERIVED** (count from capture) | Capture dropped 228 packets – may have missed additional zero‑window ads |
| Last zero‑window advertisement timestamp | 2026‑10‑07 21:00:51.949052 (same as first) | **WIRE_DERIVED** | Same limitation as above |
| Sender high‑water (observed_snd_nxt) at first zero‑window | **4 206 633** (relative) | **WIRE_DERIVED** (data packets) | May be missing earlier data due to drops |
| Sender high‑water when it becomes stationary | **N/A** – no stationary period observed | **WIRE_DERIVED** (none) | Capture may have missed a longer zero‑window episode |
| Stationary duration during zero‑window episode | **0 s** (no interval) | **WIRE_DERIVED** | Same as above |
| First positive‑window advertisement after zero‑window | 2026‑10‑07 21:00:51.949191 (raw win = 1902) | **WIRE_DERIVED** | Very short interval – could be a probe |
| First new high‑water after reopening | **4 210 785** (relative) | **WIRE_DERIVED** | Observed immediately after positive‑window ack |
| New sequence‑space progress after reopening | **4 152 bytes** | **WIRE_DERIVED** | Small; may be impacted by missing packets |
| OBSERVER_RECONSTRUCTION_GAP count (ACK > observed snd nxt) | **27** | **PASSIVE** (gap inference) | Gaps could be caused by dropped data packets (228 drops) |
| Minimum reconstructed usable‑receive credit | **0 bytes** | **PASSIVE** (credit calculation) | Credit depends on correct window scaling – assumed scale = 7 |
| Phase A (credit > 0 & data progress) | **Sufficient** – credit positive from SYN‑ACK onward and data observed increasing | **PASSIVE** | Capture loss does not hide the observed increase |
| Phase B (credit = 0 & stationary data) | **Insufficient** – only a single zero‑window packet observed, no measurable stationary high‑water interval | **PASSIVE** | 228 dropped packets may have concealed additional zero‑window ads and a stall period |
| Phase C (credit > 0 & data resumes) | **Sufficient** – positive window (win = 1902 << 7) followed by new data segment | **PASSIVE** | Dependent on the correctness of the brief positive‑window observation |
| Passive loss/congestion evidence during Phase B | **None observed** (no retransmissions, duplicate ACK bursts, ECN marks) | **PASSIVE** | Capture incompleteness could have missed such events |

## Overall classification

**RUN‑002 CLASSIFICATION: B** – FC transition is observed (zero‑window packet exists), but the 228 kernel‑dropped packets prevent reliable validation of the full A → B → C transition, especially the stationary‑high‑water interval required for Phase B.

---

*Document version: 1.0 – 2026‑10‑07*
