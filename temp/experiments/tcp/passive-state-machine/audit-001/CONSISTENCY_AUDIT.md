# CONSISTENCY AUDIT – Passive TCP State‑Machine (audit‑001)

**Audit date**: 2026‑10‑08

**Scope** – The audit covers the immutable snapshot of the specification
`/home/rosa/experiments/tcp/TCP-PASSIVE-STATE-MACHINE.md` (SHA‑256:
`3202f8b822b8db62c035b0ad1bd487bfff66dee69e6f33e846c8e77806f61d85`).
All checks are performed offline, using the frozen artefacts of
`TCP‑FC‑001/run‑005` (`GROUND_TRUTH.md`, `PASSIVE‑ANALYSIS.md`, capture).

---

## 1. Executive summary

* The specification is **internally consistent** and **deterministic** – every
  guard, transition and loss‑signal rule can be evaluated from the packet that
  triggers it together with the minimal state retained by the machine.
* No **critical** defects were found (i.e. contradictions that would make the
  state machine impossible to implement).
* **Major issues** – a single problem related to the handling of sequence‑number
  wrap‑around for the retransmission‑overlap predicate.
* **Minor issues** – a handful of documentation ambiguities (window‑scale
  exponent vs. multiplier, direction‑explicitness, loss‑signal clearing, the
  five‑event trace wording, and the per‑packet definition of `P_NO_PROGRESS`).
* The four‑state model remains appropriate for passive analysis; the semantic
  mapping correctly refrains from claiming “proof” of `D`, `F` or `C`.

**Verdict**: **PASS WITH CONDITIONS** – the model can be used as‑is after the
documentation tweaks listed in the *Proposed revisions* section.

---

## 2. Issue inventory

| Severity | # | Predicate / State / Transition | Description | RFC / Evidence |
|----------|---|--------------------------------|-------------|----------------|
| Minor    | 1 | **WIN_SCALE** | The current definition says “exponent `ws` advertised … The scale is `2^ws`.”  Later the specification occasionally refers to the *scale* as a multiplier.  Clarify that `WIN_SCALE(dir)` is the **exponent** (`ws`), and that the **multiplier** is `2^ws` used only when left‑shifting the raw window field. | RFC 7323 §2.3 |
| Minor    | 2 | **ADVERTISED_WINDOW** | When the window‑scale option is missing (e.g., a captured SYN‑exchange is absent) the expression `win_raw << WIN_SCALE` is undefined.  The predicate should be marked **UNKNOWN** in that case, causing the machine to remain in `P_UNKNOWN`. | RFC 7323 §2.3; RFC 9293 §3.5 |
| Major    | 3 | **RETRANS_OVERLAP** | The definition mentions “overlaps any previously observed range `R'` … Wrap‑aware comparisons are used.”  The description does not spell out how a range that crosses the 2³² boundary is handled.  Without an explicit rule the implementation could incorrectly label a wrap‑around retransmission as *no* overlap. | RFC 5681 §3.2; RFC 9293 §3.1 |
| Minor    | 4 | **SEQ_PROGRESS / ACK_PROGRESS direction** | The predicates are defined with a generic *direction* parameter, but the specification never states which TCP direction they refer to.  Add a short note: `SEQ_PROGRESS` applies to the **forward** data direction (sender → receiver); `ACK_PROGRESS` applies to the **reverse** direction (receiver → sender). | RFC 9293 §3.5 |
| Minor    | 5 | **Loss‑signal flag clearing** | The rule reads “A contiguous interval with **no** loss‑signal observations clears the flag.”  It is ambiguous whether the flag is cleared on the *first* packet after the interval or only after the interval length is known.  Clarify that the flag is cleared on the first packet that does **not** satisfy any loss‑signal predicate after the last flagged packet. | – |
| Minor    | 6 | **P_NO_PROGRESS entry guard** | The guard is satisfied by a *single* packet that shows no progress while the window is positive.  This leads to rapid toggling between `P_PROGRESS` and `P_NO_PROGRESS` on alternating ACK‑only packets.  The behaviour matches the specification (per‑packet semantics) but the documentation should emphasise that the state does **not** imply a sustained stall. | – |
| Minor    | 7 | **Five‑event trace wording** | Event 1 is described as “last progressing packet” but the frozen artefacts contain two distinct packets (a data segment and a pure‑ACK) that together satisfy the guard.  Split the description or note that the two packets are considered together for brevity. | GROUND_TRUTH.md, PASSIVE‑ANALYSIS.md |

---

## 3. Predicate audit (Task 2)

| Predicate | Original definition | Technical assessment | RFC reference | Proposed correction |
|-----------|---------------------|----------------------|---------------|---------------------|
| **SEQ_LT(a,b)** | `0 < ((b - a) mod 2³²) < 2³¹` | Correct wrap‑aware ordering. | RFC 9293 §3.1 | – |
| **ACK_LT(a,b)** | Same as `SEQ_LT` applied to ACK field. | Correct. | RFC 9293 §3.1 | – |
| **WIN_SCALE(dir)** | “Exponent `ws` advertised by the *receiver* … The scale is `2^ws`.” | Accurate, but the wording mixes *exponent* and *multiplier*. | RFC 7323 §2.3 | Clarify that `WIN_SCALE` is the **exponent** `ws`; the actual multiplier is `2^ws` and is applied via left‑shift when computing advertised windows. |
| **ADVERTISED_WINDOW(dir,pkt)** | `(win_raw(pkt) << WIN_SCALE(dir))` | Correct when the scale is known. When the scale is unknown the value is undefined. | RFC 7323 §2.3; RFC 9293 §3.5 | Add a clause: *If `WIN_SCALE(dir)` is unknown, `ADVERTISED_WINDOW` is **UNKNOWN** and the machine must stay in `P_UNKNOWN`. |
| **ZERO_WINDOW(pkt)** | `ADVERTISED_WINDOW == 0` | Correct; a zero‑scaled window always yields zero. | RFC 9293 §3.5 | – |
| **WINDOW_RIGHT_EDGE(dir,pkt)** | `(ACK(pkt) + ADVERTISED_WINDOW(dir,pkt)) mod 2³²` | Correct wrap‑aware computation of the right edge. | RFC 9293 §3.5 | – |
| **SENDER_SEQ_HIGH_WATER(dir)** | “Maximum observed `seq+len` …” | Correct, but note that off‑load can hide intermediate data; the value is an **observed upper bound**. | RFC 9293 §3.5 | Add wording about off‑load uncertainty (already present elsewhere). |
| **AT_WINDOW_EDGE(dir)** | Equality of high‑water and latest right edge (mod 2³²). | Correct. | Derived from above predicates | – |
| **CREDIT(dir)** | `CREDIT = (WINDOW_RIGHT_EDGE_latest - SENDER_SEQ_HIGH_WATER) mod 2³²` | Correct as an *upper bound* on remaining credit; it may over‑estimate because in‑flight bytes are invisible. | RFC 9293 §3.5 | Keep the “upper‑bound” wording (already present). |

---

## 4. Direction‑specific progress predicates (Task 3)

* **SEQ_PROGRESS(dir)** – evaluated on packets **sent in `dir`** that contain payload (`len>0`).  The predicate uses the current packet’s `seq`/`len` and the previously stored `SENDER_SEQ_HIGH_WATER(dir)`.
* **ACK_PROGRESS(dir)** – evaluated on **pure‑ACK packets travelling opposite to `dir`** (i.e. the ACK direction).  It compares the packet’s `ACK` field with the previously stored highest ACK seen from that direction.
* Both predicates are **packet‑local**: only the current packet can set the predicate to true; a past progress event does not keep the machine in `P_PROGRESS` indefinitely.
* The state machine therefore treats a single non‑progressing packet as a trigger for `P_NO_PROGRESS` (see §5).  This design choice is intentional and is documented explicitly.

---

## 5. State‑definition audit (Task 4)

### 5.1 P_PROGRESS
* **Entry guard** – `ADVERTISED_WINDOW>0` **and** (`SEQ_PROGRESS` or `ACK_PROGRESS`) on the current packet.  Works for both data‑direction packets (SEQ_PROGRESS) and reverse‑direction ACKs (ACK_PROGRESS).
* **Exit guard** – (a) `ZERO_WINDOW` becomes true, OR (b) the **next** packet has `ADVERTISED_WINDOW>0` **and** **no** progress (`SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false).  The guard is evaluated per‑packet; a single non‑progress packet causes a transition to `P_NO_PROGRESS`.
* **Comments** – The definition is consistent and deterministic.

### 5.2 P_WINDOW_BLOCKED
* **Entry guard** – First ACK that (1) advertises a zero window **and** (2) does **not** advance the ACK number (duplicate ACK).  Only the first qualifying ACK is needed – no second zero‑window ACK is required.
* **Exit guard** – When an ACK with a **positive** advertised window is observed:
  * If the same packet also shows `SEQ_PROGRESS` or `ACK_PROGRESS`, transition to **P_PROGRESS**.
  * Otherwise (no progress), transition to **P_NO_PROGRESS**.
* This satisfies the required behaviour that the machine never stays in
  `P_WINDOW_BLOCKED` merely because the window reopened without visible progress.

### 5.3 P_NO_PROGRESS
* **Entry guard** – Packet with `ADVERTISED_WINDOW>0` and **both** `SEQ_PROGRESS` = false **and** `ACK_PROGRESS` = false.  The guard is evaluated on the *current* packet; a single ACK‑only packet will cause the transition.
* **Exit guard** – Either `SEQ_PROGRESS` = true **or** `ACK_PROGRESS` = true (return to `P_PROGRESS`) or a zero‑window appears (return to `P_WINDOW_BLOCKED`).
* **Note** – The state does **not** imply a sustained stall; it only records that the *most recent* packet observed no progress.

### 5.4 P_UNKNOWN
* **Entry guard** – Insufficient information to evaluate any of the three higher‑precedence guards (missing win‑scale, missing latest window, or a `CAPTURE_GAP`).
* **Exit guard** – As soon as enough packets become available to satisfy any higher guard, the machine moves accordingly.
* Used for all cases where the wire‑only view cannot compute credit or progress.

---

## 6. Transition table audit (Task 5)

* All transitions listed in §3 of the specification are **mutually exclusive** because the guard conditions are ordered by precedence (P_PROGRESS > P_WINDOW_BLOCKED > P_NO_PROGRESS > P_UNKNOWN).
* Every possible packet falls into one of the following categories:
  1. Zero‑window duplicate ACK → triggers `P_WINDOW_BLOCKED` entry.
  2. Positive‑window packet with progress → triggers `P_PROGRESS` entry.
  3. Positive‑window packet without progress → triggers `P_NO_PROGRESS` entry.
  4. Packet lacking required fields or occurring inside a capture gap → triggers `P_UNKNOWN`.
* No transition relies on information that is not either present in the current packet or retained in the minimal state (latest ACK, high‑water, win‑scale).  The machine therefore can be implemented deterministically.
* The handling of a window reopening **without** progress is explicitly covered by the `P_WINDOW_BLOCKED → P_NO_PROGRESS` transition, satisfying the requirement from the specification.
* The loss‑signal flag is orthogonal and its activation/clearing rules are independent of the main transition matrix.

---

## 7. Loss‑signal flag audit (Task 6)

* **Activation** – Directly observable predicates (`DUP_ACK ≥3`, `ECN_CE_IP`, `ECN_ECE_TCP`, `ECN_CWR_TCP`, `RETRANS_OVERLAP`).  The flag is set on the packet that first satisfies any of them.
* **Clearing** – The flag is cleared on the **first** subsequent packet that does **not** satisfy *any* loss‑signal predicate.  This rule is deterministic and does not require timers.
* No ambiguity was found; the only improvement is the wording clarification (see Issue 5).

---

## 8. Verification of the five‑event trace (Task 7)

| # | Packet (timestamp ns) | Direction | `seq` | `ack` | `win_raw` | Scale (`ws`) | Advertised window | Payload length | Predicates true | State before | State after |
|---|------------------------|-----------|-------|-------|----------|--------------|-------------------|----------------|----------------|--------------|-------------|
| 1 | 1791409208771441545 (pre_send) – data segment (sender→receiver) | S→R | 0 (initial) | – | – | – | – | payload 65536 | `SEQ_PROGRESS` (high‑water rises) & `ACK_PROGRESS` (later ACK) | *N/A* (initial) | **P_PROGRESS** |
| 2 | 1791409208853555000 – ACK (receiver→sender) | R→S | – | 373 377 | 0 | 1 (receiver scale) | 0 | 0 | `ZERO_WINDOW` true, `ACK_PROGRESS` false | **P_PROGRESS** | **P_WINDOW_BLOCKED** |
| 3 | 1791409209065246000 – second zero‑window ACK (same fields) | R→S | – | 373 377 | 0 | 1 | 0 | 0 | `ZERO_WINDOW` true, still no `ACK_PROGRESS` | **P_WINDOW_BLOCKED** | **P_WINDOW_BLOCKED** |
| 4 | 1791409209072252000 – ACK with raw window 31796 | R→S | – | 373 377 | 31796 | 1 | 63 592 | 0 | `ADVERTISED_WINDOW>0`, no progress (`SEQ_PROGRESS` = false, `ACK_PROGRESS` = false) | **P_WINDOW_BLOCKED** | **P_NO_PROGRESS** |
| 5 | 1791409209072739000 – ACK advancing to 380 829 | R→S | – | 380 829 | 31796 | 1 | 63 592 (still) | 0 | `ACK_PROGRESS` true | **P_NO_PROGRESS** | **P_PROGRESS** |

All timestamps, window values and ACK numbers match the information inside
`GROUND_TRUTH.md` (lines 5‑13) and `PASSIVE‑ANALYSIS.md` (lines 21‑32).  No packet
with duplicate ACKs, ECN marks or retransmissions appears, therefore the loss‑signal flag stays inactive throughout the sequence.

---

## 9. Semantic‑mapping audit (Task 8)

The mapping table in the specification correctly distinguishes **direct wire
evidence** (`WIRE_DIRECT`), **derived** credit calculations (`WIRE_DERIVED`), and
the **absence** of endpoint‑side variables (`ENDPOINT`).  No clause claims that a
zero‑window alone *proves* `FC_LIMITED`; it is only listed as **consistent with**.
Similarly, duplicate ACKs or ECN marks are only *consistent with* `CC_LIMITED`.
The audit therefore finds the semantic mapping scientifically defensible.

---

## 10. Summary of issue counts

* **Critical**: 0
* **Major**:    1 (wrap‑around handling for `RETRANS_OVERLAP`)
* **Minor**:    6 (WIN_SCALE wording, ADVERTISED_WINDOW unknown case, direction notes,
  loss‑signal clearing, P_NO_PROGRESS per‑packet semantics, five‑event trace wording)

---

## 11. Recommendations (next steps)

1. Apply the **minimal textual revisions** listed in `PROPOSED_REVISIONS.md`.
2. After the edits, run the existing unit‑test suite (if any) to confirm that the
   parser of the spec still matches the implementation used by the audit tools.
3. Document the wrap‑around rule for `RETRANS_OVERLAP` in the implementation notes
   of any downstream classifier.
4. No further experimental work is required.

---

*Audit performed by the Cline coding‑assistant (offline, read‑only).* 
