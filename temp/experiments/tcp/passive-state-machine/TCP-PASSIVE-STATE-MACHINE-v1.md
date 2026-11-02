# Passive TCP Diagnostic State‑Machine Specification (v1)

**Version**: v1 – 2026‑10‑08

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
| **WIN_SCALE(dir)** | Exponent `ws` advertised by the *receiver* of direction `dir` in the SYN (or SYN‑ACK if the receiver is the server). The **multiplier** used for window calculation is `2^ws` (i.e. a left‑shift by `ws`). | 7323 §2.3 |
| **ADVERTISED_WINDOW(dir,pkt)** | `(win_raw(pkt) << WIN_SCALE(dir))` when `WIN_SCALE(dir)` is known; otherwise the value is **UNKNOWN**. | 9293 §3.5, 7323 §2.3 |
| **ZERO_WINDOW(pkt)** | `ADVERTISED_WINDOW == 0`. | 9293 §3.5 |
| **POSITIVE_WINDOW(pkt)** | `ADVERTISED_WINDOW > 0`. | – |
| **WINDOW_RIGHT_EDGE(dir,pkt)** | `(ACK(pkt) + ADVERTISED_WINDOW(dir,pkt)) mod 2³²`. | 9293 §3.5 |
| **SENDER_SEQ_HIGH_WATER(dir)** | Maximum observed `seq+len` for data segments in direction `dir` (wrap‑aware). Updated on every data packet. | 9293 §3.5 |
| **AT_WINDOW_EDGE(dir)** | `SENDER_SEQ_HIGH_WATER(dir) == WINDOW_RIGHT_EDGE_latest(dir)` (mod 2³²). | Derived |
| **SEQ_PROGRESS(dir)** | (forward direction: sender → receiver) Current packet carries data (`len>0`) and `seq+len` is **SEQ_LT** greater than the previously stored `SENDER_SEQ_HIGH_WATER(dir)`. | 9293 §3.5 |
| **ACK_PROGRESS(dir)** | (reverse direction: receiver → sender) Current packet is a pure ACK and its `ACK` field is **ACK_LT** greater than the previously stored ACK number from the opposite direction. | 9293 §3.5 |
| **DUP_ACK(dir, n≥3)** | `n` consecutive pure‑ACK packets from the opposite direction with identical ACK numbers and no intervening higher ACK. | 5681 §3.2 |
| **ECN_CE_IP(pkt)** | IPv4/IPv6 ECN field equals `0b11` (Congestion Experienced). | 3168 |
| **ECN_ECE_TCP(pkt)** | TCP **ECE** flag set on an ACK packet. | 3168 |
| **ECN_CWR_TCP(pkt)** | TCP **CWR** flag set on an ACK packet. | 3168 |
| **RETRANS_OVERLAP(dir, seg)** | Let `R = [seq, seq+len)` for `seg`. `seg` is a retransmission candidate iff:\n> 1. `R` **wrap‑aware overlaps** any previously observed range `R'` for the same direction (including partial overlap and identical ranges), **and**\n> 2. No ACK covering `max(end(R), end(R'))` (using `ACK_LT`) was observed between the first occurrence of `R'` and `seg`.\nThe overlap test must correctly handle intervals that cross the 2³² wrap point. | 5681 §3.2 |
| **CAPTURE_GAP(prev_ts, cur_ts)** | Explicit discontinuity reported by the capture format (drop count > 0 or timestamp jump flagged). Distinct from a silent idle period. | – |
| **OFFLOAD_INDICATOR(seg)** | Segment length > typical MSS or a large sequence jump (>64 KiB without intervening ACKs), indicating possible TSO/GSO. | – |

The predicate **CREDIT(dir)** is a *derived upper bound* on remaining sender credit:

```text
CREDIT = (WINDOW_RIGHT_EDGE_latest - SENDER_SEQ_HIGH_WATER) mod 2³²
```

Because in‑flight bytes are not observable, this value may be larger than the true
available credit.  When a `CAPTURE_GAP` occurs the credit calculation is marked
*uncertain*.

---

## 2. Direction‑aware processing and retained state

### 2.1 Retained variables per direction `dir`

* `CURRENT_ADVERTISED_WINDOW(dir)` – most recent value of `ADVERTISED_WINDOW` (or UNKNOWN) observed from a reverse‑direction ACK packet.
* `ZERO_WINDOW_ACTIVE(dir)` – derived flag (`CURRENT_ADVERTISED_WINDOW(dir) == 0`).
* `SENDER_SEQ_HIGH_WATER(dir)` – maximum `seq+len` observed on forward‑direction data packets.
* `LAST_ACK(dir)` – latest ACK number observed on reverse‑direction packets.
* `CAPTURE_GAP_ACTIVE` – true when a `CAPTURE_GAP(prev_ts, cur_ts)` predicate occurs; uncertain predicates are treated as UNKNOWN while active.

### 2.2 Deterministic packet‑processing algorithm (the core of the passive machine)

For **each packet** the analyser performs the steps below **in order**:

1. **Identify packet direction** (forward = sender → receiver, reverse = receiver → sender) using the known client/server IP/port tuple.
2. **Read the previous retained state** (`CURRENT_ADVERTISED_WINDOW`, `ZERO_WINDOW_ACTIVE`, `SENDER_SEQ_HIGH_WATER`, `LAST_ACK`).
3. **Evaluate sequence/ACK progress** against the previous values:
   * Forward packet → evaluate `SEQ_PROGRESS` using the prior `SENDER_SEQ_HIGH_WATER`.
   * Reverse packet → evaluate `ACK_PROGRESS` using the prior `LAST_ACK`.
4. **Evaluate the current receiver‑window advertisement** if the packet provides a `win_raw` field (i.e. reverse‑direction ACK):
   * Compute `ZERO_WINDOW` / `POSITIVE_WINDOW` directly from `win_raw` (sign predicates).
   * If `WIN_SCALE` is known, compute `ADVERTISED_WINDOW`; otherwise the value is **UNKNOWN**.
5. **Otherwise (no window field)**, reuse the latest retained receiver‑window condition (`CURRENT_ADVERTISED_WINDOW` and `ZERO_WINDOW_ACTIVE`).
6. **Evaluate applicable transition guards** using the results from steps 3‑5.  Predicates that are *not applicable* (e.g., `ACK_PROGRESS` on a forward data packet) are marked **NOT_APPLICABLE**, not FALSE.  If a predicate cannot be evaluated because a required field is missing (e.g., unknown `WIN_SCALE`), it yields **UNKNOWN**.
7. **Select the resulting observational state** according to the guard precedence **P_PROGRESS → P_WINDOW_BLOCKED → P_NO_PROGRESS → P_UNKNOWN**.
8. **Update retained values** *after* the state selection:
   * Forward data packet – update `SENDER_SEQ_HIGH_WATER` to `max(previous, seq+len)`.
   * Reverse ACK packet – store the newly computed `CURRENT_ADVERTISED_WINDOW` (or UNKNOWN) and update `LAST_ACK`.
   * Any packet – if a `CAPTURE_GAP` predicate is observed, set `CAPTURE_GAP_ACTIVE` until a subsequent packet without a gap clears it.
9. **Emit any discrete loss‑related events** (see §4).  A reverse‑direction ACK that re‑opens the window can cause a state transition on the *same* packet (i.e., step 7 uses the freshly observed window advertisement).

This algorithm guarantees that the machine never erases the most recent receiver‑window
condition when processing a forward‑direction data segment, satisfying the requirement
that a forward packet must not automatically clear a previously observed zero‑window.

---

## 3. Passive states (four primary states)

Precedence (higher overrides lower): **P_PROGRESS** → **P_WINDOW_BLOCKED** → **P_NO_PROGRESS** → **P_UNKNOWN**.

### 3.1 State definitions

| State | Entry guard (observable) | Exit guard (observable) | Evidence required | Uncertainty handling |
|-------|--------------------------|------------------------|-------------------|----------------------|
| **P_PROGRESS** | `ADVERTISED_WINDOW > 0` **and** (`SEQ_PROGRESS` **or** `ACK_PROGRESS`) on the current packet. | – `ZERO_WINDOW` becomes true **or** (`SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false) on a subsequent packet while the window stays > 0. | Data segment that advances the high‑water **or** ACK that advances the ACK number, with a positive advertised window. | If a `CAPTURE_GAP` starts while the guard holds, the state stays **P_PROGRESS** but is flagged *uncertain* (progress may have continued or stopped). |
| **P_WINDOW_BLOCKED** | First ACK that satisfies both: (1) `ZERO_WINDOW` true, (2) `ACK_PROGRESS` = false (duplicate ACK). No second ACK is required. | When a later ACK has `ADVERTISED_WINDOW > 0` **and** (`SEQ_PROGRESS` or `ACK_PROGRESS`) in the *same* packet, transition to **P_PROGRESS**. If the same packet re‑opens the window but shows no progress, transition to **P_NO_PROGRESS**. | A single zero‑window ACK without progress is sufficient. | If a `CAPTURE_GAP` occurs before a positive‑window ACK is seen, the state remains **P_WINDOW_BLOCKED** but is flagged *uncertain*. |
| **P_NO_PROGRESS** | Packet with `ADVERTISED_WINDOW > 0` **and** both `SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false (i.e. no progress observed in that packet). | `SEQ_PROGRESS` = true **or** `ACK_PROGRESS` = true → **P_PROGRESS**; `ZERO_WINDOW` → **P_WINDOW_BLOCKED**. | Positive‑window ACKs (or data packets) that do **not** advance either sequence or ack number. | A `CAPTURE_GAP` within a stagnation region keeps the state but marks it *uncertain*. |
| **P_UNKNOWN** | Insufficient information to evaluate the three guards above (missing window‑scale, missing latest window advertisement, or a capture gap that erases the needed packet). | As soon as enough packets become available to evaluate any higher‑precedence guard, transition accordingly. | Absence of the required fields or explicit `CAPTURE_GAP` that blocks computation. | By definition the state is *unknown*; no further uncertainty flag is needed. |

### 3.2 Transition table (deterministic, no time‑outs)

| From → To | Trigger (packet condition) | Required fields | Directly observed or derived? | Data retained for future checks |
|-----------|----------------------------|-----------------|-------------------------------|----------------------------------|
| **P_UNKNOWN → P_PROGRESS** | First packet with `ADVERTISED_WINDOW>0` **and** (`SEQ_PROGRESS` or `ACK_PROGRESS`). | `seq`, `len`, `ACK`, `win`, TCP options (scale). | Directly observed. | Store `WIN_SCALE`, latest `ACK`, `WINDOW_RIGHT_EDGE`, `SENDER_SEQ_HIGH_WATER`. |
| **P_UNKNOWN → P_WINDOW_BLOCKED** | First zero‑window duplicate ACK (conditions from entry guard). | `ACK`, `win`. | Directly observed. | Store latest `ACK`, note zero‑window. |
| **P_UNKNOWN → P_NO_PROGRESS** | Positive‑window packet with neither `SEQ_PROGRESS` nor `ACK_PROGRESS`. | `ACK`, `win`. | Directly observed. | Keep new window value. |
| **P_PROGRESS → P_WINDOW_BLOCKED** | Zero‑window duplicate ACK observed while in `P_PROGRESS`. | `ACK`, `win`. | Directly observed. | Record zero‑window. |
| **P_PROGRESS → P_NO_PROGRESS** | Positive‑window packet with no progress (`SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false). | `ACK`, `win`. | Directly observed. | Keep new window value. |
| **P_PROGRESS → P_PROGRESS** | Packet with either `SEQ_PROGRESS` = true **or** `ACK_PROGRESS` = true (window still > 0). | `seq`, `len`, `ACK`. | Directly observed. | Update high‑water / ACK. |
| **P_WINDOW_BLOCKED → P_PROGRESS** | ACK with `ADVERTISED_WINDOW>0` **and** (`SEQ_PROGRESS` or `ACK_PROGRESS`) in the *same* packet. | `ACK`, `win`. | Directly observed. | Update window and high‑water / ACK. |
| **P_WINDOW_BLOCKED → P_NO_PROGRESS** | ACK with `ADVERTISED_WINDOW>0` **and** no progress (`SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false). | `ACK`, `win`. | Directly observed. | Keep new window value. |
| **P_NO_PROGRESS → P_PROGRESS** | Packet with either `SEQ_PROGRESS` = true **or** `ACK_PROGRESS` = true (window still > 0). | `seq`, `len`, `ACK`. | Directly observed. | Update high‑water / ACK. |
| **P_NO_PROGRESS → P_WINDOW_BLOCKED** | Zero‑window duplicate ACK observed. | `ACK`, `win`. | Directly observed. | Record zero‑window. |
| **Any state → P_UNKNOWN** | `CAPTURE_GAP` that deletes the most‑recent window‑advertisement or missing window‑scale; cannot evaluate higher‑precedence guards. | – | Derived. | Keep previous values, mark *uncertain*. |

All transitions are triggered **solely** by the packet currently being processed;
no timeout‑based transitions are used.

---

## 4. Event‑only loss evidence (no persistent flag)

Loss‑related observations are recorded as discrete events.  The passive machine does
not maintain a Boolean `loss_signal_active` flag.

* `EVENT_DUP_ACK` – three or more duplicate ACKs observed.
* `EVENT_ECN_CE` – ECN Congestion‑Experienced observed in the IP header.
* `EVENT_ECN_ECE`, `EVENT_ECN_CWR` – TCP ECN flags set.
* `EVENT_RETRANS_OVERLAP` – retransmission overlap detected (wrap‑aware rule).

These events are **evidence** that loss or congestion may have occurred, but they
do **not** by themselves imply the transport state `CC_LIMITED`.  The semantic
mapping therefore only treats them as *consistent with* congestion‑control
limitations.

---

## 5. Five‑event trace (TCP‑FC‑001/run‑005)

The captured packets are listed below.  No frame numbers are provided because the
`tcpdump` output used to generate the trace does not include an explicit frame ID.
Timestamps, directions, ACK numbers, raw window values and scaling are recorded
exactly as they appear in the pcap.

| Event | Timestamp (ns) | Direction | `seq` → `seq+len` | `ack` | `win_raw` | `WIN_SCALE` | Advertised window (scaled) | Payload length | `SEQ_PROGRESS` | `ACK_PROGRESS` | `ZERO_WINDOW` | `POSITIVE_WINDOW` | Resulting state |
|-------|----------------|-----------|-------------------|-------|-----------|------------|----------------------------|----------------|----------------|----------------|----------------|-------------------|-----------------|
| 1 | 1791409208825478 | **forward** (client → server) | 372 141 → 373 377 | 1 | 502 (sender’s own window) | – | – | 1 236 B | **TRUE** | NOT_APPLICABLE | – | – | **P_PROGRESS** |
| 2 | 1791409208853555 | **reverse** (server → client) | – | 373 377 | 0 | 1 (scale from SYN‑ACK) | 0 B | 0 B | NOT_APPLICABLE | **FALSE** | **TRUE** | **FALSE** | **P_WINDOW_BLOCKED** |
| 3 | 1791409209065246 | **reverse** | – | 373 377 | 0 | 1 | 0 B | 0 B | NOT_APPLICABLE | **FALSE** | **TRUE** | **FALSE** | **P_WINDOW_BLOCKED** |
| 4 | 1791409209072252 | **reverse** | – | 373 377 | 31 796 | 1 | 63 592 B (`31 796 << 1`) | 0 B | NOT_APPLICABLE | **FALSE** | **FALSE** | **TRUE** | **P_NO_PROGRESS** |
| 5 | 1791409209072739 | **reverse** | – | 380 829 | 44 251 | 1 | 88 502 B (`44 251 << 1`) | 0 B | NOT_APPLICABLE | **TRUE** | **FALSE** | **TRUE** | **P_PROGRESS** |

The sequence of passive states is therefore:

```
P_PROGRESS → P_WINDOW_BLOCKED → P_WINDOW_BLOCKED → P_NO_PROGRESS → P_PROGRESS
```

No loss‑signal events are observed in this trace.

---

## 6. Mapping to semantic transport states (conservative)

| Semantic state | Passive evidence that **supports / is consistent with** the state | What remains **unknowable** (cannot be proved) |
|----------------|---------------------------------------------------------------|-----------------------------------------|
| **READY** | Observation of **P_PROGRESS** with no loss‑signal events active (positive window and progress). | Internal predicates **D** (pending data) and **C** (congestion‑window headroom) are not observable. |
| **APP_LIMITED** | **P_NO_PROGRESS** while the window stays positive and no loss‑signal events are active. This pattern is compatible with the sender having no data ready, but the observation does not reveal the sender’s buffer state. | Whether the sender actually has pending data (**D**) or whether congestion‑control would have limited it (**C**). |
| **FC_LIMITED** | **P_WINDOW_BLOCKED** with no loss‑signal events active (zero‑window observed). The stall is compatible with the receiver having closed its receive credit. | Whether the sender had data ready (**D**) or would have been limited by congestion (**C**). |
| **CC_LIMITED** | Positive window (**P_PROGRESS** or **P_NO_PROGRESS**) **and** any loss‑signal event observed (duplicate ACK burst, ECN‑CE, or retransmission) **and** lack of progress (i.e. **P_NO_PROGRESS** or low‑frequency progress). This is consistent with congestion‑control limiting the sender. | The exact congestion‑window size (**C**) and any pending data (**D**). |
| **MULTIPLE** | Overlap of **P_WINDOW_BLOCKED** and an active loss‑signal event within the same observation window (e.g., zero‑window ACKs interleaved with duplicate ACKs). | The relative contribution of flow‑control vs. congestion‑control cannot be separated. |

No passive observation can **prove** any semantic state because the definitions of **D**, **F**, **C** require internal kernel state.  The mapping therefore uses the terms **supports / consistent with** only.

---

## 7. Observability limitations (what cannot be inferred from passive capture)

| Limitation | What remains unknown |
|------------|----------------------|
| Internal sender variables (`snd_cwnd`, `snd_nxt`, `snd_una`) | Exact congestion‑window headroom (**C**) and exact amount of data already sent but not yet acknowledged. |
| Sender write‑buffer state | Whether the application has pending data (**D**). |
| Precise remaining receiver‑window credit | `CREDIT` is only an upper bound; the true usable credit may be smaller because in‑flight bytes are invisible. |
| Loss without duplicate‑ACK/ECN | Hidden packet loss leaves the loss‑signal events false even though loss occurred. |
| Off‑load effects (TSO/GSO) | Large coalesced segments hide intermediate sequence numbers, reducing granularity of `SEQ_PROGRESS`. |
| Capture gaps that delete the latest window advertisement | During a gap the machine cannot know whether the window reopened or stayed closed; the current state is retained but flagged *uncertain*. |
| Missing SYN‑exchange (no negotiated window‑scale) | Without the receiver’s scale, `ADVERTISED_WINDOW` cannot be interpreted; the state stays **P_UNKNOWN**. |

These limitations are intrinsic to any passive, wire‑only analysis and are reflected
in the **P_UNKNOWN** state and the *uncertain* markings throughout the specification.
