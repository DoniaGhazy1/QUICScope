# Design Resolution – Passive TCP State‑Machine (audit‑001)

**Date**: 2026‑10‑08

This document records the unresolved design issues identified during the
consistency audit, the corrective proposals, and the remaining decisions that
require researcher approval before any changes are merged into the authoritative
`TCP-PASSIVE-STATE-MACHINE.md`.

---

## 1. Original problems

1. **Direction‑aware packet processing** – The original specification mixed the
   forward‑direction `SEQ_PROGRESS` predicate with the reverse‑direction
   `ACK_PROGRESS` predicate, effectively treating every packet as if it could
   contribute to both sequence‑ and acknowledgment‑progress.  This created
   ambiguity about which retained state (sender high‑water or receiver ACK) should
   be updated for a given packet and what the state machine should do when a
   packet lacks the fields needed for a particular guard.

2. **Loss‑signal flag clearing** – The audit introduced a rule that clears the
   flag on the *first* ordinary packet after a loss‑signal interval.  The rule
   was not justified scientifically and would require an additional “clearing
   condition” that the original design never defined.

3. **Five‑event trace** – The trace used in the audit relied on `sender_timeline`
   CSV entries (application‑level observations) rather than packets directly
   observed in the wire capture.  This violated the “wire‑only” principle of the
   passive specification.

4. **Window‑scale handling** – The predicates `WIN_SCALE` and `ADVERTISED_WINDOW`
   did not explicitly describe the behaviour when the scaling option was not
   negotiated (e.g., missing SYN exchange) or when a zero‑window advertisement
   is observed.  The spec also forced a transition to `P_UNKNOWN` in cases where
   the necessary scaling exponent is unknown, even though the raw window field
   is still observable.

---

## 2. Corrected definitions (provisional – to be merged after approval)

### 2.1 WIN_SCALE
* **Definition** – `WIN_SCALE(dir)` is the *exponent* `ws` advertised by the
  receiver of direction `dir` in the SYN (client → server) or SYN‑ACK (server →
  client).  The **multiplier** used for window calculation is `2^ws`.
* **Unknown case** – If no SYN/SYN‑ACK containing a window‑scale option is seen,
  `WIN_SCALE(dir)` is **UNKNOWN**.

### 2.2 ADVERTISED_WINDOW
* **When `WIN_SCALE` is known** – `(win_raw(pkt) << WIN_SCALE(dir))` (raw 16‑bit
  `win` left‑shifted by the exponent).
* **When `WIN_SCALE` is UNKNOWN** – the value of `ADVERTISED_WINDOW` is **UNKNOWN**;
  the machine must remain in `P_UNKNOWN` for any predicate that depends on a
  numeric window value.

### 2.3 ZERO_WINDOW
* `ZERO_WINDOW(pkt)` is true **iff** `ADVERTISED_WINDOW(pkt) == 0`.
* If `ADVERTISED_WINDOW` is UNKNOWN, `ZERO_WINDOW` is not applicable (the guard
  cannot be evaluated), and the packet is processed under the `P_UNKNOWN`
  precedence.

### 2.4 Positive‑window detection
* `ADVERTISED_WINDOW > 0` is evaluatable only when `WIN_SCALE` is known.
* When the exponent is unknown the predicate is **UNKNOWN**, leading again to
  `P_UNKNOWN`.

---

## 3. Direction‑aware processing algorithm

The passive analyser must first determine the **direction** of each packet
using the known client and server IP/port tuple (e.g., `192.168.88.20:36040`
→ `192.168.88.21:5203` is *forward*).  The algorithm then evaluates predicates
according to the table below.

| Direction | Evaluated predicates (per packet) | State‑update actions |
|-----------|-----------------------------------|----------------------|
| **Forward** (sender → receiver) | *Data‑segment* (`len>0`): `SEQ_PROGRESS`.  The packet also carries an `ACK` field, but **`ACK_PROGRESS` is **not** evaluated** for forward packets.  `ZERO_WINDOW`, `ADVERTISED_WINDOW` are *not applicable* because the sender does not advertise a receive window. | – Update `SENDER_SEQ_HIGH_WATER(dir)` with `max(previous, seq+len)`.  – Update `LAST_ACK(dir)` with the `ACK` field (optional for later loss‑signal checks). |
| **Reverse** (receiver → sender) | *Pure ACK* (`len==0`): `ACK_PROGRESS`, `ZERO_WINDOW`, `ADVERTISED_WINDOW`.  `SEQ_PROGRESS` is **not** evaluated because no data payload is present. | – Update `LAST_ACK(dir)` with the `ACK` value.  – Update `CURRENT_ADVERTISED_WINDOW(dir)` with `ADVERTISED_WINDOW` (or UNKNOWN). |
| **Any** | Loss‑signal predicates (`DUP_ACK`, `ECN_*`, `RETRANS_OVERLAP`) are evaluated whenever the required fields are present, regardless of direction. | – Set/retain loss‑signal flag according to the chosen loss‑signal model (see Section 4). |

**Handling missing fields** – If a predicate requires a field that is absent in the packet (e.g., a forward data segment has no window field), the predicate is marked **NOT‑APPLICABLE** rather than FALSE.  The transition guard uses only the predicates that are applicable; if none of the guard conditions can be evaluated, the machine falls back to the `P_UNKNOWN` precedence.

---

## 4. Loss‑signal model – alternatives

### 4.1 Option A – Event‑only model
* **Description** – Every observation that satisfies a loss‑signal predicate is
  recorded as a discrete *event* (e.g., `DUP_ACK`, `ECN_ECE`, `RETRANS_OVERLAP`).
  No persistent “loss flag” is maintained.
* **Scientific meaning** – The model makes no claim about the duration of loss
  or congestion; it merely reports the evidence that was observed on the wire.
* **Implementation** – Simpler: the analyser emits a log entry for each event and
  never needs to decide when the flag should be cleared.

### 4.2 Option B – Persistent evidence model
* **Description** – A Boolean `loss‑signal` flag is set when any loss‑signal
  predicate becomes true and remains true until an *explicit* clearing
  condition is observed (e.g., a packet that satisfies **none** of the loss‑
  signal predicates **and** is known to be a normal data/ACK packet).
* **Scientific meaning** – Implies that loss‑related behaviour may persist
  beyond the observed packet, which is not directly justified by the passive
  capture alone.
* **Implementation** – Requires a deterministic clearing rule.  The rule
  proposed in the audit (“clear on the first ordinary packet”) conflates lack of
  loss evidence with an implicit time‑based interval, which is not scientifically
  defensible.

### 4.3 Recommendation
The **event‑only model (Option A)** is the simpler, scientifically defensible
choice.  It avoids unjustified assumptions about the duration of loss and
requires no additional clearing logic.  The design may still expose a *loss‑
signal* event stream for downstream analysis, but it will not maintain a
persistent flag.

---

## 5. Wire‑only five‑event trace (TCP‑FC‑001/run‑005)

The trace below is reconstructed **solely from packets** in `capture.pcap`
using `tcpdump`.  Frame numbers correspond to the line numbers in the filtered
view (i.e., the order of the displayed packets) and are provided for reference
only.

| # | Frame (≈) | Timestamp (ns) | Direction | `seq` → `seq+len` | `ack` | `win_raw` | `WIN_SCALE` | Advertised window (scaled) | Payload length | Predicate evaluations (applicable) | Resulting passive state |
|---|-----------|----------------|-----------|-------------------|-------|-----------|------------|----------------------------|----------------|-----------------------------------|--------------------------|
| 1 | 38 | 1791409208825478 ns | **forward** (client→server) | 372 141 → 373 377 | 1 | 502 (sender‑side) | – | – | 1 236 B | `SEQ_PROGRESS = true` (high‑water advanced). `ACK_PROGRESS` not evaluated for forward packet. | **P_PROGRESS** |
| 2 | 39 | 1791409208853555 ns | **reverse** (server→client) | – | 373 377 | 0 | 1 (scale from SYN‑ACK) | 0 B | 0 B | `ZERO_WINDOW = true`. `ACK_PROGRESS = false`. | **P_WINDOW_BLOCKED** |
| 3 | 42 | 1791409209065246 ns | **reverse** | – | 373 377 | 0 | 1 | 0 B | 0 B | `ZERO_WINDOW = true`. `ACK_PROGRESS = false`. | **P_WINDOW_BLOCKED** |
| 4 | 46 | 1791409209072252 ns | **reverse** | – | 373 377 | 31 796 | 1 | 63 592 B (`31 796 << 1`) | 0 B | `ADVERTISED_WINDOW > 0`. `SEQ_PROGRESS = false`. `ACK_PROGRESS = false`. | **P_NO_PROGRESS** |
| 5 | 46 | 1791409209072739 ns | **reverse** | – | 380 829 | 44 251 | 1 | 88 502 B (`44 251 << 1`) | 0 B | `ADVERTISED_WINDOW > 0`. `ACK_PROGRESS = true` (ACK increased). | **P_PROGRESS** |

All timestamps are expressed in nanoseconds for consistency with the frozen
ground‑truth files.

**Note** – The capture was inspected with `tcpdump`, which does not assign an
explicit frame‑number field.  The numbers above are the line indices in the
filtered output and should be treated as relative identifiers.

---

## 6. Remaining uncertainties

1. **Exact clearing condition for a persistent loss‑signal flag** – If the
   research team prefers Option B, a rigorously defined clearing predicate must
   be agreed upon (e.g., a packet that simultaneously satisfies `ACK_PROGRESS`
   *and* `ADVERTISED_WINDOW > 0` *and* no loss‑signal predicates).  Until such a
   definition is provided the event‑only model remains the safest choice.
2. **Window‑scale negotiation edge cases** – The current proposal treats a
   missing SYN‑exchange as `WIN_SCALE = UNKNOWN`.  Some downstream tools may
   prefer to fall back to a scale of 0 (no scaling) rather than UNKNOWN; this
   decision should be coordinated with the classifier implementation.

---

## 7. Recommended specification changes (to be applied after approval)

* Adopt the **direction‑aware processing algorithm** (Section 3) and replace the
  mixed‑direction guards.
* Update the **WIN_SCALE** and **ADVERTISED_WINDOW** definitions as in
  Sections 2.1‑2.4.
* Remove the current loss‑signal flag clearing wording and, if the event‑only
  model is chosen, delete the orthogonal flag description entirely.
* Replace the five‑event trace description with the wire‑only table from
  Section 5.
* Clarify that predicates whose required fields are absent are *not‑applicable*
  rather than false, and that the machine falls back to `P_UNKNOWN` only when a
  guard cannot be evaluated.

---

*Prepared by the Cline coding‑assistant (offline, read‑only).*
