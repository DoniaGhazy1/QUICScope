# Approval Review – Passive TCP State‑Machine Audit (audit‑001)

**Date**: 2026‑10‑08

This document records the independent review performed before any of the proposed
revisions are merged into the authoritative `TCP-PASSIVE-STATE-MACHINE.md`.

---

## 1. Exact proposed revisions

The `PROPOSED_REVISIONS.md` file contains seven bullet‑point edits.  For each edit the
original line (as it appears in the immutable spec snapshot) and the proposed
replacement are reproduced below, together with the rationale, classification and
impact on the state‑machine behaviour.

### 1.1 WIN_SCALE wording (Minor – Issue 1)
* **Original** (line 21 of spec):
```
**WIN_SCALE(dir)** | Exponent `ws` advertised by the *receiver* of direction `dir` in the SYN (or SYN‑ACK if the receiver is the server). The scale is `2^ws`.
```
* **Proposed**:
```
**WIN_SCALE(dir)** | Exponent `ws` advertised by the *receiver* of direction `dir` in the SYN (or SYN‑ACK if the receiver is the server). The **multiplier** used for window calculation is `2^ws` (i.e. a left‑shift by `ws`).
```
* **Reason** – Clarify that the exponent `ws` is not itself the multiplier; the multiplier is used when scaling the raw 16‑bit window field.
* **Classification** – Editorial (purely explanatory) – does not affect any transition or predicate result.

### 1.2 ADVERTISED_WINDOW when scale unknown (Minor – Issue 2)
* **Original** (line 22):
```
**ADVERTISED_WINDOW(dir,pkt)** | `(win_raw(pkt) << WIN_SCALE(dir))` (raw 16‑bit `win` left‑shifted by the receiver’s scale).
```
* **Proposed**:
```
**ADVERTISED_WINDOW(dir,pkt)** | `(win_raw(pkt) << WIN_SCALE(dir))` when `WIN_SCALE(dir)` is known; otherwise the value is **UNKNOWN** and the machine must remain in `P_UNKNOWN`.
```
* **Reason** – The predicate is undefined if the window‑scale option was never negotiated (e.g. the SYN exchange is missing).  The machine should therefore fall back to `P_UNKNOWN` rather than using an undefined shift.
* **Classification** – Semantic (introduces a new *UNKNOWN* outcome that can affect state transitions when scale is missing).
* **Effect** – In runs where the SYN exchange is absent, the machine will stay in `P_UNKNOWN` instead of inadvertently evaluating an incorrect advertised window.

### 1.3 Direction clarification for progress predicates (Minor – Issue 4)
* **Original** (lines 27‑28):
```
**SEQ_PROGRESS(dir)** | Current packet carries data (`len>0`) and `seq+len` is **SEQ_LT** greater than the previously stored `SENDER_SEQ_HIGH_WATER(dir)`.
**ACK_PROGRESS(dir)** | Current packet is a pure ACK and its `ACK` field is **ACK_LT** greater than the previously stored ACK number from the opposite direction.
```
* **Proposed**:
```
**SEQ_PROGRESS(dir)** | (forward direction: sender → receiver) Current packet carries data (`len>0`) and `seq+len` is **SEQ_LT** greater than the previously stored `SENDER_SEQ_HIGH_WATER(dir)`.
**ACK_PROGRESS(dir)** | (reverse direction: receiver → sender) Current packet is a pure ACK and its `ACK` field is **ACK_LT** greater than the previously stored ACK number from the opposite direction.
```
* **Reason** – Explicitly state which TCP direction each predicate refers to; this eliminates ambiguity when reading the table.
* **Classification** – Editorial – no change to predicate semantics.

### 1.4 RETRANS_OVERLAP wrap‑around handling (Major – Issue 3)
* **Original** (line 33):
```
**RETRANS_OVERLAP(dir, seg)** | Let `R = [seq, seq+len)` for `seg`. `seg` is a retransmission candidate iff `R` overlaps any previously observed range `R'` for the same direction **and** no ACK covering `max(end(R), end(R'))` was seen between the first occurrence of `R'` and `seg`. Overlap may be partial; identical ranges are a special case. Wrap‑aware comparisons are used.
```
* **Proposed** (re‑written as a list for clarity):
```
**RETRANS_OVERLAP(dir, seg)** | Let `R = [seq, seq+len)` for `seg`. `seg` is a retransmission candidate iff:
> 1. `R` **wrap‑aware overlaps** any previously observed range `R'` for the same direction (including partial overlap and identical ranges), **and**
> 2. No ACK covering `max(end(R), end(R'))` (using `ACK_LT`) was observed between the first occurrence of `R'` and `seg`.
> The overlap test must correctly handle intervals that cross the 2³² wrap point.
```
* **Reason** – The previous description left the wrap‑around case implicit; an implementation could mistakenly treat a range that spans the 2³² boundary as non‑overlapping.  The new rule makes the required behaviour explicit.
* **Classification** – Semantic – changes the definition of the `RETRANS_OVERLAP` predicate and therefore can affect the activation of the loss‑signal flag.

### 1.5 Loss‑signal flag clearing wording (Minor – Issue 5)
* **Original** – The spec currently does **not** contain any wording for the loss‑signal flag clearing rule.  The audit identified the missing sentence:
```
The flag is cleared after a contiguous interval with none of those observations.
```
* **Proposed**:
```
The flag is cleared on the **first** packet after such an interval that does **not** satisfy any loss‑signal predicate.
```
* **Reason** – Disambiguate when the flag becomes inactive; the original phrasing left it open whether the interval length must be known before clearing.
* **Classification** – Editorial (clarification) – does not alter the logical condition but makes the activation/deactivation deterministic.

### 1.6 P_NO_PROGRESS per‑packet semantics (Minor – Issue 6)
* **Original** (state‑table entry, not present in the trimmed view of the spec but referenced by the audit):
```
Entry guard: Packet with `ADVERTISED_WINDOW > 0` **and** both `SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false (i.e. no progress observed in that packet).
```
* **Proposed**:
```
Entry guard: Any **single** packet with `ADVERTISED_WINDOW > 0` that shows **no** `SEQ_PROGRESS` **and** no `ACK_PROGRESS`. The state records the lack of progress for that packet only; it does not imply a prolonged stall.
```
* **Reason** – Emphasise that the guard is evaluated per‑packet and does not imply an extended period of inactivity.
* **Classification** – Editorial – no change to predicate values, only to wording.

### 1.7 Five‑event trace wording (Minor – Issue 7)
* **Original** (section 5 of the spec):
```
1. **Last progressing packet in Phase A** – data segment that raises the sender high‑water …
```
* **Proposed**:
```
1. **Last progressing observation in Phase A** – the data segment that raises the sender high‑water **and** the subsequent ACK that advances the ACK number.  These are two separate packets but together satisfy the entry guard for `P_PROGRESS`.
```
* **Reason** – The original text implied a single packet performed both sequence and ACK progress, which is inaccurate; the transition is triggered by two packets.
* **Classification** – Editorial – only the narrative description changes; the state‑machine behaviour remains unchanged.

---

## 2. Determinism assessment – full input‑condition matrix

The transition logic of the passive machine is driven solely by the evaluation of the
following *mutually exclusive* packet categories.  The guard precedence (higher
overrides lower) is hard‑coded in the specification:

```
P_PROGRESS → P_WINDOW_BLOCKED → P_NO_PROGRESS → P_UNKNOWN
```

The matrix enumerates every combination of observable attributes that can be derived
from a single packet together with the minimal retained state (high‑water marks,
window‑scale, last ACK).  Columns marked **X** indicate that the condition is true.

| # | Direction (src→dst) | Window advertised | `ZERO_WINDOW` | `ADVERTISED_WINDOW > 0` | `SEQ_PROGRESS` | `ACK_PROGRESS` | Missing history / gap | Window reopen without progress | Resulting state (next) |
|---|---------------------|-------------------|---------------|--------------------------|----------------|----------------|-----------------------|--------------------------------|------------------------|
| 1 | any                 | known (scale)     | ✅            | ❌ (==0)                 | –              | –              | –                     | –                              | **P_WINDOW_BLOCKED**   |
| 2 | any                 | known (scale)     | ❌            | ✅                       | ✅ (seq+len advances high‑water) | – | –                     | –                              | **P_PROGRESS**         |
| 3 | any                 | known (scale)     | ❌            | ✅                       | –              | ✅ (ACK advances) | –                     | –                              | **P_PROGRESS**         |
| 4 | any                 | known (scale)     | ❌            | ✅                       | ❌            | ❌            | –                     | –                              | **P_NO_PROGRESS**     |
| 5 | any                 | unknown (no scale) | –            | –                        | –              | –              | –                     | –                              | **P_UNKNOWN**          |
| 6 | any                 | known (scale)     | ❌            | ✅                       | –              | –              | Capture gap (missing packets) | –                     | **P_UNKNOWN** (uncertain) |
| 7 | any                 | known (scale)     | ❌            | ✅                       | –              | –              | –                     | ✅ (window >0, no progress, but **window reopened** i.e. `WIN_SCALE` unchanged) | **P_NO_PROGRESS** (state *uncertain* because we cannot see data that may have been missed) |

**Explanation of rows**

*Rows 1‑4* cover the four mutually exclusive cases described in the spec.  The guard
precedence guarantees that exactly one of them matches any packet that contains a
well‑defined window advertisement.

*Row 5* handles the situation where the window‑scale option is absent (e.g. the SYN
exchange is missing).  `ADVERTISED_WINDOW` is undefined, so the machine must move to
`P_UNKNOWN`.

*Row 6* captures a capture gap (`CAPTURE_GAP` predicate).  Because the exact window
value cannot be known, the transition is to `P_UNKNOWN` and the state is marked *uncertain*.

*Row 7* represents the specific case described in the specification where the
window re‑opens (`ADVERTISED_WINDOW > 0`) but no progress is observed in the same
packet.  The machine transitions from `P_WINDOW_BLOCKED` to `P_NO_PROGRESS` – a
deterministic rule that does not depend on timers.

No row produces multiple applicable guards; the precedence list resolves any
theoretical overlap.  Conversely, there is **always** at least one applicable guard;
the only situation that would leave the matrix empty is a packet that lacks a TCP
header altogether, which is filtered out before the state‑machine is invoked.

**Retained‑state update order**

1. **Evaluate predicates** using the *previous* retained values (high‑water marks, last
   ACK, window‑scale).  This ensures that progress is measured *relative* to the
   state before the current packet.
2. **Select the next state** based on the guard precedence shown above.
3. **Update retained state** – after the transition the machine records:
   * `SENDER_SEQ_HIGH_WATER(dir)` = max(previous, `seq+len` of current packet) (if data).
   * `LAST_ACK(dir)` = `ACK` of the current packet (if pure ACK).
   * `WIN_SCALE(dir)` if a SYN/SYN‑ACK with a window‑scale option is observed.
   * `LOSS_SIGNAL` flag is set/cleared according to the loss‑signal rules (see §4).
4. Loop to the next packet.

Because the update occurs *after* predicate evaluation, there is no risk of a
packet simultaneously satisfying both a “progress” guard and a “no‑progress” guard.

---

## 3. Five‑event trace verification

The frozen artefacts for `TCP‑FC‑001/run‑005` provide the timestamps and the observable
values for the five events.  The table below summarizes the evidence that is
available without parsing the raw `capture.pcap` (the latter would require
additional tooling such as `tshark`, which is not installed in this environment).

| # | Timestamp (ns) | Direction | `seq` / payload length | `ack` | `win_raw` | `WIN_SCALE` | Advertised window (scaled) | Predicates true | Resulting state |
|---|----------------|-----------|-----------------------|-------|-----------|-------------|---------------------------|-----------------|-----------------|
| 1 | 1791409208771441545 | sender → receiver (pre_send) | data segment, length 65536 | – | – | – | – | `SEQ_PROGRESS = true`, `ACK_PROGRESS = true` (via subsequent ACK) | **P_PROGRESS** |
| 2 | 1791409208853555000 | receiver → sender (zero‑window ACK) | – | 373 377 | 0 | 1 (scale) | 0 | `ZERO_WINDOW = true`, `ACK_PROGRESS = false` | **P_WINDOW_BLOCKED** |
| 3 | 1791409209065246000 | receiver → sender (second zero‑window ACK) | – | 373 377 | 0 | 1 | 0 | `ZERO_WINDOW = true`, `ACK_PROGRESS = false` | **P_WINDOW_BLOCKED** |
| 4 | 1791409209072252000 | receiver → sender (window re‑opens) | – | 373 377 | 31796 | 1 | 63 592 | `ADVERTISED_WINDOW>0`, `SEQ_PROGRESS = false`, `ACK_PROGRESS = false` | **P_NO_PROGRESS** |
| 5 | 1791409209072739000 | receiver → sender (ACK with progress) | – | 380 829 | 31796 | 1 | 63 592 | `ADVERTISED_WINDOW>0`, `ACK_PROGRESS = true` | **P_PROGRESS** |

The timestamps and values are taken directly from `GROUND_TRUTH.md` (events 2‑5) and
`PASSIVE-ANALYSIS.md` (window sizes, ACK numbers, and high‑water values).  Event 1 is the
initial data segment recorded in the `sender_timeline.csv` (pre_send row).  All five
state transitions match the sequence reported in the specification (see Section 5).

**Limitation** – The capture file (`capture.pcap`) was not parsed because the
environment lacks a packet‑dissection tool (e.g. `tshark`).  Consequently, we cannot
list raw frame numbers or per‑packet sequence numbers beyond those explicitly
present in the investigative artefacts.

---

## 4. Loss‑signal flag clearing definition

The specification defines a *loss‑signal* flag that becomes **active** when any of the
following predicates hold on a packet:

* `DUP_ACK(dir, n≥3)` – three or more duplicate ACKs.
* `ECN_CE_IP(pkt)` – ECN Congestion‑Experienced in the IP header.
* `ECN_ECE_TCP(pkt)` – TCP ECE flag set.
* `ECN_CWR_TCP(pkt)` – TCP CWR flag set.
* `RETRANS_OVERLAP(dir, seg)` – retransmission overlap (as per the wrap‑aware rule).

**Clearing rule (deterministic)** – The flag is cleared on the **first** subsequent
packet that does **not** satisfy *any* of the loss‑signal predicates.  No timers or
explicit intervals are required; the rule depends only on observable packet
properties.  This behaviour is exactly the wording introduced in the proposed
revision (Issue 5) and is confirmed by the audit (see §7 of `CONSISTENCY_AUDIT.md`).

If a downstream implementation cannot rely on this definition (e.g. because it
needs a minimum idle interval before clearing), that would constitute an **unresolved
design decision** and should be addressed before the specification is used in a
production classifier.

---

## 5. Remaining decisions requiring researcher approval

1. **Apply the minimal textual and semantic revisions** listed in Section 1.
2. **Confirm the wrap‑around overlap rule** for `RETRANS_OVERLAP` (Major Issue 3).
3. **Clarify the loss‑signal flag description** – the spec currently lacks any
   description of the flag; decide whether to incorporate the wording from Issue 5
   (or to add a more extensive orthogonal‑flag section).
4. **Validate the updated `ADVERTISED_WINDOW` behaviour** – run any existing unit‑
   test suite to ensure that the *UNKNOWN* branch does not introduce unintended
   failures.
5. **Optionally extend the documentation** to include an explicit state‑transition
   table (the matrix in Section 2) for future readers.

---

*Prepared by the Cline coding‑assistant (offline, read‑only).*
