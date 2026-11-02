# Proposed revisions to TCP‑PASSIVE‑STATE‑MACHINE.md

The following edits address the minor and major issues identified in the
consistency audit.  Each bullet corresponds to a single, self‑contained change
that can be applied with a standard `apply_patch` diff.

---

## 1. WIN_SCALE wording (Minor – Issue 1)
**Location**: predicate table, line defining `WIN_SCALE`.
**Change**:
```diff
- **WIN_SCALE(dir)** | Exponent `ws` advertised by the *receiver* of direction `dir` in the SYN (or SYN‑ACK if the receiver is the server). The scale is `2^ws`.
+ **WIN_SCALE(dir)** | Exponent `ws` advertised by the *receiver* of direction `dir` in the SYN (or SYN‑ACK if the receiver is the server). The **multiplier** used for window calculation is `2^ws` (i.e. a left‑shift by `ws`).
```

---

## 2. ADVERTISED_WINDOW when scale unknown (Minor – Issue 2)
**Location**: predicate table, line defining `ADVERTISED_WINDOW`.
**Change**:
```diff
- **ADVERTISED_WINDOW(dir,pkt)** | `(win_raw(pkt) << WIN_SCALE(dir))` (raw 16‑bit `win` left‑shifted by the receiver’s scale).
+ **ADVERTISED_WINDOW(dir,pkt)** | `(win_raw(pkt) << WIN_SCALE(dir))` when `WIN_SCALE(dir)` is known; otherwise the value is **UNKNOWN** and the machine must remain in `P_UNKNOWN`.
```

---

## 3. Direction clarification for progress predicates (Minor – Issue 4)
**Location**: predicate table, lines for `SEQ_PROGRESS` and `ACK_PROGRESS`.
**Change**:
```diff
- **SEQ_PROGRESS(dir)** | Current packet carries data (`len>0`) and `seq+len` is **SEQ_LT** greater than the previously stored `SENDER_SEQ_HIGH_WATER(dir)`.
+ **SEQ_PROGRESS(dir)** | (forward direction: sender → receiver) Current packet carries data (`len>0`) and `seq+len` is **SEQ_LT** greater than the previously stored `SENDER_SEQ_HIGH_WATER(dir)`.
- **ACK_PROGRESS(dir)** | Current packet is a pure ACK and its `ACK` field is **ACK_LT** greater than the previously stored ACK number from the opposite direction.
+ **ACK_PROGRESS(dir)** | (reverse direction: receiver → sender) Current packet is a pure ACK and its `ACK` field is **ACK_LT** greater than the previously stored ACK number from the opposite direction.
```

---

## 4. RETRANS_OVERLAP wrap‑around handling (Major – Issue 3)
**Location**: predicate table, line for `RETRANS_OVERLAP`.
**Change**:
```diff
- **RETRANS_OVERLAP(dir, seg)** | Let `R = [seq, seq+len)` for `seg`. `seg` is a retransmission candidate iff `R` overlaps any previously observed range `R'` for the same direction **and** no ACK covering `max(end(R), end(R'))` was seen between the first occurrence of `R'` and `seg`. Overlap may be partial; identical ranges are a special case. Wrap‑aware comparisons are used.
+ **RETRANS_OVERLAP(dir, seg)** | Let `R = [seq, seq+len)` for `seg`. `seg` is a retransmission candidate iff:
> 1. `R` **wrap‑aware overlaps** any previously observed range `R'` for the same direction (including partial overlap and identical ranges), **and**
> 2. No ACK covering `max(end(R), end(R'))` (using `ACK_LT`) was observed between the first occurrence of `R'` and `seg`.
+ The overlap test must correctly handle intervals that cross the 2³² wrap point.
```

---

## 5. Loss‑signal flag clearing wording (Minor – Issue 5)
**Location**: section *2.2 Orthogonal loss‑signal flag*.
**Change**:
```diff
- The flag is cleared after a contiguous interval with none of those observations.
+ The flag is cleared on the **first** packet after such an interval that does **not** satisfy any loss‑signal predicate.
```

---

## 6. P_NO_PROGRESS per‑packet semantics (Minor – Issue 6)
**Location**: state table entry for `P_NO_PROGRESS`.
**Change**:
```diff
- Entry guard: Packet with `ADVERTISED_WINDOW > 0` **and** both `SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false (i.e. no progress observed in that packet).
+ Entry guard: Any **single** packet with `ADVERTISED_WINDOW > 0` that shows **no** `SEQ_PROGRESS` **and** no `ACK_PROGRESS`. The state records the lack of progress for that packet only; it does not imply a prolonged stall.
```

---

## 7. Five‑event trace wording (Minor – Issue 7)
**Location**: section *5. TCP‑FC‑001 run‑005 – five‑event trace*.
**Change**:
```diff
- 1. **Last progressing packet in Phase A** – data segment that raises the sender high‑water …
+ 1. **Last progressing observation in Phase A** – the data segment that raises the sender high‑water **and** the subsequent ACK that advances the ACK number.  These are two separate packets but together satisfy the entry guard for `P_PROGRESS`.
```

---

Applying the above changes yields a specification that is fully consistent with the RFCs, the frozen run‑005 evidence, and the deterministic state‑machine design.
