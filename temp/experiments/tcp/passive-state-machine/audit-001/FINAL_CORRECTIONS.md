# FINAL CORRECTIONS – Passive TCP State‑Machine (audit‑001)

**Date**: 2026‑10‑08

This document captures the last set of offline design refinements that must be
reviewed and approved before the passive state‑machine specification is frozen.

---

## 1. Corrected window‑scale handling (split into sign vs. numeric size)

### 1.A Window‑sign predicates (do **not** depend on scaling)

* **ZERO_WINDOW(pkt)** – true **iff** `win_raw(pkt) == 0`.
* **POSITIVE_WINDOW(pkt)** – true **iff** `win_raw(pkt) > 0`.

These predicates are purely observational and are evaluable for any TCP ACK
packet, regardless of whether a window‑scale option was negotiated.

### 1.B Numeric advertised window

* **WIN_SCALE(dir)** – exponent `ws` advertised by the *receiver* of direction
  `dir` in the *SYN* (client → server) or *SYN‑ACK* (server → client).  The multiplier
  is `2^ws`.  If the SYN/SYN‑ACK containing a window‑scale option is **missing**
  from the capture, `WIN_SCALE(dir)` is **UNKNOWN**.
* **ADVERTISED_WINDOW(dir, pkt)** –
  *If* `WIN_SCALE(dir)` is known: `(win_raw(pkt) << WIN_SCALE(dir))` (raw 16‑bit
  window left‑shifted by the exponent).  *If* `WIN_SCALE(dir)` is UNKNOWN: the
  predicate value is **UNKNOWN**.

### 1.C Handshake nuances

*When the capture contains the initial SYN/SYN‑ACK* – the scaling exponent is
  extracted from the TCP options and used for all subsequent `ADVERTISED_WINDOW`
  calculations.
*When the handshake is absent* – the machine cannot know whether the endpoints
  negotiated a scale of 0 (no scaling) or omitted the option entirely.  In both
  cases `WIN_SCALE` is treated as UNKNOWN, which forces `ADVERTISED_WINDOW` to
  be UNKNOWN and any guard that needs a numeric window to fall back to the
  `P_UNKNOWN` precedence.

---

## 2. Corrected direction‑aware state‑retention model

The passive analyser must retain **both** the latest observed receiver‑window
condition *and* the sender‑side high‑water mark, without one overwriting the
other.

### 2.1 Retained variables per direction `dir`

* `CURRENT_ADVERTISED_WINDOW(dir)` – the most recent value of `ADVERTISED_WINDOW`
  (or UNKNOWN) observed from a reverse‑direction ACK packet.
* `ZERO_WINDOW_ACTIVE(dir)` – derived from `CURRENT_ADVERTISED_WINDOW(dir) == 0`.
* `SENDER_SEQ_HIGH_WATER(dir)` – maximum `seq+len` observed on forward‑direction
  data packets.
* `LAST_ACK(dir)` – latest ACK number observed on reverse‑direction packets.
* `CAPTURE_GAP_ACTIVE` – true when a `CAPTURE_GAP(prev_ts, cur_ts)` predicate is
  observed; the state machine should treat any dependent predicates as UNKNOWN.

### 2.2 Evaluation order for each packet (deterministic)

1. **Determine packet direction** using the known 4‑tuple.
2. **Update retained variables** **after** predicate evaluation (so guards use the
   values that existed *before* the current packet):
   * For a **forward** packet (`len>0`):
     - Evaluate `SEQ_PROGRESS` against the *previous* `SENDER_SEQ_HIGH_WATER`.
     - Do **not** modify `CURRENT_ADVERTISED_WINDOW` or `ZERO_WINDOW_ACTIVE`.
     - After guard processing, set `SENDER_SEQ_HIGH_WATER = max(prev, seq+len)`.
   * For a **reverse** packet (`len==0`):
     - Evaluate `ZERO_WINDOW` / `POSITIVE_WINDOW` using `win_raw` (sign predicates).
     - If `WIN_SCALE` is known, compute `ADVERTISED_WINDOW`; otherwise treat it as UNKNOWN.
     - Evaluate `ACK_PROGRESS` against the *previous* `LAST_ACK`.
     - After guard processing, store the newly computed `CURRENT_ADVERTISED_WINDOW`
       and update `LAST_ACK`.
   * For **any** packet, evaluate loss‑signal predicates and handle the loss‑signal
     model (event‑only, see §4).
3. **Apply guard precedence** (`P_PROGRESS` → `P_WINDOW_BLOCKED` → `P_NO_PROGRESS`
   → `P_UNKNOWN`).  Guards that depend on a numeric window (`ADVERTISED_WINDOW > 0`)
   are only considered when the value is known; otherwise the guard is regarded
   as NOT‑APPLICABLE and the machine falls back to `P_UNKNOWN`.
4. **Capture‑gap handling** – when a `CAPTURE_GAP` predicate occurs, set
   `CAPTURE_GAP_ACTIVE = true`.  While active, any predicate requiring a numeric
   window or sequence continuity is treated as UNKNOWN, causing the machine to
   transition to `P_UNKNOWN` (unless a higher‑precedence guard like `P_PROGRESS`
   can be evaluated).  The flag is cleared when a packet without a gap is seen.

### 2.3 Counter‑example demonstrating the previous algorithm’s flaw

*Scenario:* a forward data segment arrives **after** the receiver has advertised
`win_raw = 0` (zero‑window).  In the earlier version the forward packet’s
evaluation of `SEQ_PROGRESS` would update `SENDER_SEQ_HIGH_WATER` **and**
implicitly clear the stored zero‑window information, causing the machine to
miss the fact that the receiver’s window was still closed.  Consequently the
state could incorrectly jump from `P_WINDOW_BLOCKED` to `P_PROGRESS` without an
intervening *window‑reopen* event.

*Correct behaviour:* the forward packet updates only the sender‑side high‑water
mark; the retained `CURRENT_ADVERTISED_WINDOW` (and thus `ZERO_WINDOW_ACTIVE`)
remains unchanged until an actual reverse‑direction ACK with a non‑zero window
is observed.  This preserves the logical ordering of events observed on the wire.

---

## 3. Verified five‑event trace (TCP‑FC‑001/run‑005)

The capture was inspected with `tcpdump`.  Because `tcpdump` does not emit an
explicit frame number, the identifiers are omitted; timestamps, directions, ACK
numbers, raw window values and scaling are recorded exactly as they appear in
the pcap.

| Event | Timestamp (ns) | Direction | `seq` → `seq+len` | `ack` | `win_raw` | `WIN_SCALE` | Advertised window (scaled) | Payload length | Predicates evaluated (applicable) | Resulting passive state |
|-------|----------------|-----------|-------------------|-------|-----------|------------|----------------------------|----------------|-----------------------------------|--------------------------|
| 1 | 1791409208825478 | **forward** (client → server) | 372 141 → 373 377 | 1 | 502 (sender’s own window) | – | – | 1 236 B | `SEQ_PROGRESS = true`. `ACK_PROGRESS` not evaluated (forward). | **P_PROGRESS** |
| 2 | 1791409208853555 | **reverse** (server → client) | – | 373 377 | 0 | 1 (scale from SYN‑ACK) | 0 B | 0 B | `ZERO_WINDOW = true`. `ACK_PROGRESS = false`. | **P_WINDOW_BLOCKED** |
| 3 | 1791409209065246 | **reverse** | – | 373 377 | 0 | 1 | 0 B | 0 B | `ZERO_WINDOW = true`. `ACK_PROGRESS = false`. | **P_WINDOW_BLOCKED** |
| 4 | 1791409209072252 | **reverse** | – | 373 377 | 31 796 | 1 | 63 592 B (`31 796 << 1`) | 0 B | `POSITIVE_WINDOW = true`. `SEQ_PROGRESS = false`. `ACK_PROGRESS = false`. | **P_NO_PROGRESS** |
| 5 | 1791409209072739 | **reverse** | – | 380 829 | 44 251 | 1 | 88 502 B (`44 251 << 1`) | 0 B | `POSITIVE_WINDOW = true`. `ACK_PROGRESS = true`. | **P_PROGRESS** |

*Why events 4 and 5 share the same line number in the previous filtered view:* the line‑number we displayed earlier was simply the **output‑line index** of the `tcpdump` command, not the pcap’s internal frame identifier.  The two packets occur at distinct timestamps (≈ 0.9 µs apart) and have different `win_raw` values, so they are separate frames.

---

## 4. Revised semantic mapping (loss‑signal EVENT‑ONLY model)

The mapping from passive states to the high‑level transport semantics (READY, APP_LIMITED, FC_LIMITED, CC_LIMITED, MULTIPLE) must not rely on a persistent `loss_signal_active` flag.

* **Loss‑related observations** are now recorded as discrete events:
  * `EVENT_DUP_ACK` – three or more duplicate ACKs observed.
  * `EVENT_ECN_CE` – ECN Congestion‑Experienced observed in the IP header.
  * `EVENT_ECN_ECE` / `EVENT_ECN_CWR` – TCP ECN flags set.
  * `EVENT_RETRANS_OVERLAP` – retransmission overlap detected (using the wrap‑aware rule).
* These events are **evidence** that loss or congestion may have occurred, but they do *not* automatically imply the transport state `CC_LIMITED`.  The semantic mapping therefore only **states that are consistent with** the observed events; it never claims proof of congestion control behaviour.
* The passive states (`P_PROGRESS`, `P_WINDOW_BLOCKED`, `P_NO_PROGRESS`, `P_UNKNOWN`) remain the basis for mapping to the higher‑level semantic states, with the same conservative reasoning as before.

---

## 5. Remaining unresolved issues

1. **Exact clearing rule for a persistent loss‑signal flag** – If the research team later decides to adopt the persistent‑flag model (Option B), a deterministic clearing predicate must be defined.  Until then the EVENT‑ONLY model stands.
2. **Window‑scale default for missing handshake** – Some downstream tools may prefer to treat a missing SYN exchange as a scale of 0 (no scaling) rather than UNKNOWN.  The team should agree on the preferred convention.

---

*Prepared by the Cline coding‑assistant (offline, read‑only).*\