# Passive TCP Diagnostic State‑Machine Specification

**Purpose** – Provide a read‑only, wire‑only specification that maps what can be
observed in a TCP capture to a four‑state passive machine and, separately, to the
semantic transport states used in the research (READY, APP_LIMITED, FC_LIMITED,
CC_LIMITED, MULTIPLE).  The specification does **not** attempt to infer internal
kernel variables such as `snd_cwnd`, `snd_nxt` or the sender’s write‑buffer.

---

## 1. Wire‑observable predicates (wire‑only, no time‑outs)

All predicates are evaluated on a **single packet** (or on the most recent packet
when a guard needs a stored value).  Wrap‑aware arithmetic follows RFC 9293 §3.1
(`SEQ_LT` / `ACK_LT`).

| Predicate | Formal definition | RFC source |
|-----------|-------------------|------------|
| **SEQ_LT(a,b)** | `0 < ((b - a) mod 2³²) < 2³¹` | 9293 §3.1 |
| **ACK_LT(a,b)** | Same as `SEQ_LT` applied to the ACK field. | 9293 §3.1 |
| **WIN_SCALE(dir)** | Exponent `ws` advertised by the *receiver* of direction `dir` in the SYN (or SYN‑ACK if the receiver is the server). The scale is `2^ws`. | 7323 §2.3 |
| **ADVERTISED_WINDOW(dir,pkt)** | `(win_raw(pkt) << WIN_SCALE(dir))` (raw 16‑bit `win` left‑shifted by the receiver’s scale). | 9293 §3.5, 7323 §2.3 |
| **ZERO_WINDOW(pkt)** | `ADVERTISED_WINDOW == 0`. | 9293 §3.5 |
| **WINDOW_RIGHT_EDGE(dir,pkt)** | `(ACK(pkt) + ADVERTISED_WINDOW(dir,pkt)) mod 2³²`. | 9293 §3.5 |
| **SENDER_SEQ_HIGH_WATER(dir)** | Maximum observed `seq+len` for data segments in direction `dir` (wrap‑aware). Updated on every data packet. | 9293 §3.5 |
| **AT_WINDOW_EDGE(dir)** | `SENDER_SEQ_HIGH_WATER(dir) == WINDOW_RIGHT_EDGE_latest(dir)` (mod 2³²). | Derived |
| **SEQ_PROGRESS(dir)** | Current packet carries data (`len>0`) and `seq+len` is **SEQ_LT** greater than the previously stored `SENDER_SEQ_HIGH_WATER(dir)`. | 9293 §3.5 |
| **ACK_PROGRESS(dir)** | Current packet is a pure ACK and its `ACK` field is **ACK_LT** greater than the previously stored ACK number from the opposite direction. | 9293 §3.5 |
| **DUP_ACK(dir, n≥3)** | `n` consecutive pure‑ACK packets from the opposite direction with identical ACK numbers and no intervening higher ACK. | 5681 §3.2 |
| **ECN_CE_IP(pkt)** | IPv4/IPv6 ECN field equals `0b11` (Congestion Experienced). | 3168 |
| **ECN_ECE_TCP(pkt)** | TCP **ECE** flag set on an ACK packet. | 3168 |
| **ECN_CWR_TCP(pkt)** | TCP **CWR** flag set on an ACK packet. | 3168 |
| **RETRANS_OVERLAP(dir, seg)** | Let `R = [seq, seq+len)` for `seg`. `seg` is a retransmission candidate iff `R` overlaps any previously observed range `R'` for the same direction **and** no ACK covering `max(end(R), end(R'))` was seen between the first occurrence of `R'` and `seg`. Overlap may be partial; identical ranges are a special case. Wrap‑aware comparisons are used. | 5681 §3.2 |
| **CAPTURE_GAP(prev_ts, cur_ts)** | Explicit discontinuity reported by the capture format (drop count > 0 or timestamp jump flagged). Distinct from a silent idle period. | – |
| **OFFLOAD_INDICATOR(seg)** | Segment length > typical MSS or a large sequence jump (>64 KiB) without intervening ACKs, indicating possible TSO/GSO. | – |

The predicate **CREDIT(dir)** is a *derived upper bound* on remaining sender credit:

```
CREDIT = (WINDOW_RIGHT_EDGE_latest - SENDER_SEQ_HIGH_WATER) mod 2³²
```

Because in‑flight bytes are not observable, this value may be larger than the true
available credit.  When a `CAPTURE_GAP` occurs the credit calculation is marked
*uncertain*.

---

## 2. Passive states (four primary states)

Precedence (higher overrides lower): **P_PROGRESS** → **P_WINDOW_BLOCKED** →
**P_NO_PROGRESS** → **P_UNKNOWN**.

### 2.1 State definitions

| State | Entry guard (observable) | Exit guard (observable) | Evidence required | Uncertainty handling |
|-------|--------------------------|--------------------------|-------------------|----------------------|
| **P_PROGRESS** | `ADVERTISED_WINDOW > 0` **and** (`SEQ_PROGRESS` **or** `ACK_PROGRESS`) on the current packet. | – `ZERO_WINDOW` becomes true **or** (`SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false) on a subsequent packet while the window stays > 0. | Data segment that advances the high‑water OR ACK that advances the ACK number, with a positive advertised window. | If a `CAPTURE_GAP` starts while the guard holds, the state stays **P_PROGRESS** but is flagged *uncertain* (progress may have continued or stopped). |
| **P_WINDOW_BLOCKED** | First ACK that satisfies both: (1) `ZERO_WINDOW` true, (2) `ACK_PROGRESS` = false (duplicate ACK). No second ACK is required. | When a later ACK has `ADVERTISED_WINDOW > 0` **and** (`SEQ_PROGRESS` **or** `ACK_PROGRESS`) in the *same* packet, transition to **P_PROGRESS**. If the same packet re‑opens the window but shows no progress, transition to **P_NO_PROGRESS**. | Two consecutive zero‑window ACKs are *not* required; the first qualifying zero‑window ACK is enough. | If a `CAPTURE_GAP` occurs before a positive‑window ACK is seen, the state remains **P_WINDOW_BLOCKED** but is flagged *uncertain*. |
| **P_NO_PROGRESS** | Packet with `ADVERTISED_WINDOW > 0` **and** both `SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false (i.e. no progress observed in that packet). | `SEQ_PROGRESS` = true **or** `ACK_PROGRESS` = true → **P_PROGRESS**; `ZERO_WINDOW` → **P_WINDOW_BLOCKED**. | Positive‑window ACKs (or data packets) that do **not** advance either sequence or ack number. | A `CAPTURE_GAP` within a stagnation region keeps the state but marks it *uncertain*. |
| **P_UNKNOWN** | Insufficient information to evaluate the three guards above (missing window‑scale, missing latest window advertisement, or a capture gap that erases the needed packet). | As soon as enough packets become available to evaluate any higher‑precedence guard, transition accordingly. | Absence of the required fields or explicit `CAPTURE_GAP` that blocks computation. | By definition the state is *unknown*; no further uncertainty flag is needed. |

### 2.2 Orthogonal loss‑signal flag

*Loss‑signal* is a **boolean flag** that can be **active** when any of the following
predicates are observed (in either direction): `DUP_ACK (≥3)`, `ECN_CE_IP`,
`ECN_ECE_TCP`, `ECN_CWR_TCP`, or `RETRANS_OVERLAP`. It is cleared after a
contiguous interval with none of those observations. The flag does **not** affect the
primary state machine but is attached to the current state for semantic mapping.

---

## 3. Transition table (deterministic, no time‑outs)

| From → To | Trigger (packet condition) | Required fields | Directly observed or derived? | Data retained for future checks |
|-----------|----------------------------|-----------------|-------------------------------|----------------------------------|
| **P_UNKNOWN → P_PROGRESS** | First packet with `ADVERTISED_WINDOW>0` **and** (`SEQ_PROGRESS` or `ACK_PROGRESS`). | `seq`, `len`, `ACK`, `win`, TCP options (scale). | Directly observed. | Store `WIN_SCALE`, latest `ACK`, `WINDOW_RIGHT_EDGE`, `SENDER_SEQ_HIGH_WATER`. |
| **P_UNKNOWN → P_WINDOW_BLOCKED** | First zero‑window duplicate ACK (conditions from entry guard). | `ACK`, `win`. | Directly observed. | Store latest `ACK`, note zero‑window. |
| **P_UNKNOWN → P_NO_PROGRESS** | Positive‑window packet with neither progress nor duplicate ACK. | `ACK`, `win`. | Directly observed. | Store advertised window. |
| **P_PROGRESS → P_PROGRESS** | Current packet continues to show progress (`SEQ_PROGRESS` or `ACK_PROGRESS`) with window > 0. | Same as entry guard. | Directly observed. | Update high‑water / latest ACK. |
| **P_PROGRESS → P_WINDOW_BLOCKED** | Current packet is a zero‑window duplicate ACK (entry guard). | `ACK`, `win`. | Directly observed. | Record zero‑window. |
| **P_PROGRESS → P_NO_PROGRESS** | Current packet has `ADVERTISED_WINDOW>0` but **neither** `SEQ_PROGRESS` nor `ACK_PROGRESS`. | `ACK`, `win`. | Directly observed. | Keep window value. |
| **P_WINDOW_BLOCKED → P_PROGRESS** | Packet with `ADVERTISED_WINDOW>0` **and** (`SEQ_PROGRESS` or `ACK_PROGRESS`) **in the same packet**. | `seq`, `len`, `ACK`, `win`. | Directly observed. | Update high‑water / ACK. |
| **P_WINDOW_BLOCKED → P_NO_PROGRESS** | Packet with `ADVERTISED_WINDOW>0` **and** no progress (`SEQ_PROGRESS` = false, `ACK_PROGRESS` = false). | `ACK`, `win`. | Directly observed. | Keep new window value. |
| **P_NO_PROGRESS → P_PROGRESS** | Packet with either `SEQ_PROGRESS` = true **or** `ACK_PROGRESS` = true (window still > 0). | `seq`, `len`, `ACK`. | Directly observed. | Update high‑water / ACK. |
| **P_NO_PROGRESS → P_WINDOW_BLOCKED** | Zero‑window duplicate ACK observed. | `ACK`, `win`. | Directly observed. | Record zero‑window. |
| **Any → *Loss‑signal* active** | Observation of any loss‑signal predicate (see orthogonal flag). | Relevant fields per predicate. | Directly observed. | Set flag. |
| **Any → *Loss‑signal* cleared** | A contiguous interval with **no** loss‑signal observations. | – | Derived (requires remembering the last loss‑signal). | Clear flag. |
| **Any state → P_UNKNOWN** | `CAPTURE_GAP` that deletes the most‑recent window‑advertisement or missing window‑scale; cannot evaluate higher‑precedence guards. | – | Derived. | Keep previous values, mark *uncertain*. |

All transitions are triggered **solely** by the packet currently being processed; no timeout‑based transitions are used.

---

## 4. Mapping to semantic transport states (external, unchanged)

| Semantic state | Passive evidence that **supports / is consistent with** the state | What remains **unknowable** (cannot be proved) |
|----------------|---------------------------------------------------------------|-----------------------------------------|
| **READY** | Observation of **P_PROGRESS** with the loss‑signal flag **inactive** (positive window and progress). | Internal predicates **D** (pending data) and **C** (congestion‑window headroom) are not observable; we cannot prove the sender is not limited by either. |
| **APP_LIMITED** | **P_NO_PROGRESS** while the window stays positive and loss‑signal is inactive. This pattern is compatible with the sender having no data ready, but the observation does not reveal the sender’s buffer state. | Whether the sender actually has pending data (**D**) or whether congestion‑control would have limited it (**C**). |
| **FC_LIMITED** | **P_WINDOW_BLOCKED** with loss‑signal inactive (zero‑window observed). The stall is compatible with the receiver having closed its receive credit. | Whether the sender had data ready (**D**) or would have been limited by congestion (**C**). |
| **CC_LIMITED** | Positive window (**P_PROGRESS** or **P_NO_PROGRESS**) **and** loss‑signal flag active (duplicate ACK burst, ECN‑CE, or retransmission) **and** lack of progress (i.e. **P_NO_PROGRESS** or low‑frequency progress). This is consistent with congestion‑control limiting the sender. | The exact congestion‑window size (**C**) and any pending data (**D**). |
| **MULTIPLE** | Overlap of **P_WINDOW_BLOCKED** and an active loss‑signal flag within the same observation window (e.g., zero‑window ACKs interleaved with duplicate ACKs). | The relative contribution of flow‑control vs. congestion‑control cannot be separated. |

No passive observation can **prove** any semantic state because the definitions of **D**, **F**, **C** require internal kernel state. The mapping therefore uses the terms **supports / consistent with** only.

---

## 5. TCP‑FC‑001 run‑005 – five‑event trace (state after each event)

The frozen artefacts (`GROUND_TRUTH.md`, `PASSIVE‑ANALYSIS.md`) provide the
following concrete packets (timestamps are nanoseconds, values taken directly
from the capture).

1. **Last progressing packet in Phase A** – data segment that raises the
   sender high‑water to 373 376 B and an ACK that advances the ACK number.
   *Predicates*: `ADVERTISED_WINDOW>0`, `SEQ_PROGRESS = true`, `ACK_PROGRESS = true`.
   **Resulting state** → **P_PROGRESS**.

2. **First zero‑window ACK** – ACK with `win_raw = 0`, ACK number = 373 377 (duplicate).
   *Predicates*: `ZERO_WINDOW = true`, `ACK_PROGRESS = false`.
   **Resulting state** → **P_WINDOW_BLOCKED** (first qualifying zero‑window ACK).

3. **Second zero‑window ACK** – another ACK with `win_raw = 0` and the same ACK number.
   *Predicates*: still `ZERO_WINDOW = true`, still no progress.
   **Resulting state** → **P_WINDOW_BLOCKED** (state unchanged).

4. **First positive‑window ACK (window re‑opens)** – ACK with `win_raw = 31796`
   (scale = 1 → advertised window = 63 592 B) **and** the ACK number **still** 373 377.
   *Predicates*: `ADVERTISED_WINDOW>0`, `SEQ_PROGRESS = false`, `ACK_PROGRESS = false`.
   According to the exit rule for `P_WINDOW_BLOCKED`, the window has reopened
   **without** any progress in the same packet, so the machine transitions to
   **P_NO_PROGRESS** (the state is *uncertain* because we cannot see whether the
   sender transmitted data that was missed). 
   **Resulting state** → **P_NO_PROGRESS**.

5. **First ACK showing renewed progress** – ACK with ACK number = 380 829 (increase).
   *Predicates*: `ADVERTISED_WINDOW>0`, `ACK_PROGRESS = true`.
   **Resulting state** → **P_PROGRESS**.

Thus the observed sequence of states is:

```
P_PROGRESS → P_WINDOW_BLOCKED → P_WINDOW_BLOCKED → P_NO_PROGRESS → P_PROGRESS
```

The loss‑signal flag stays **inactive** throughout the trace (no duplicate‑ACK
burst, ECN marking, or retransmission was observed).

---

## 6. Observability limitations (what cannot be inferred from passive capture)

| Limitation | What remains unknown |
|------------|----------------------|
| Internal sender variables (`snd_cwnd`, `snd_nxt`, `snd_una`) | Exact congestion‑window headroom (**C**) and exact amount of data already sent but not yet acknowledged. |
| Sender write‑buffer state | Whether the application has pending data (**D**). |
| Precise remaining receiver‑window credit | `CREDIT` is only an upper bound; the true usable credit may be smaller because in‑flight bytes are invisible. |
| Loss without duplicate‑ACK/ECN | Hidden packet loss leaves the loss‑signal flag false even though loss occurred. |
| Off‑load effects (TSO/GSO) | Large coalesced segments hide intermediate sequence numbers, reducing granularity of `SEQ_PROGRESS`. |
| Capture gaps that delete the latest window advertisement | During a gap the machine cannot know whether the window reopened or stayed closed; the current state is retained but flagged *uncertain*. |
| Missing SYN‑exchange (no negotiated window‑scale) | Without the receiver’s scale, `ADVERTISED_WINDOW` cannot be interpreted; the state stays **P_UNKNOWN**. |

These limitations are intrinsic to any passive, wire‑only analysis and are
reflected in the **P_UNKNOWN** state and the *uncertain* markings throughout the
specification.
