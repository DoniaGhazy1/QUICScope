# Validation Report – Passive TCP State‑Machine Specification v1

**Date**: 2026‑10‑08

### 1. Five‑event trace verification

Re‑playing the five‑event capture (Section 5 of the spec) yields the exact state
sequence `P_PROGRESS → P_WINDOW_BLOCKED → P_WINDOW_BLOCKED → P_NO_PROGRESS →
P_PROGRESS`.  No loss‑signal events are observed, confirming the transition table
behaviour.

### 2. Synthetic scenario checks (manual reasoning)

* **Zero‑window entry** – reverse ACK with `win_raw = 0` and no ACK progress leads to `P_WINDOW_BLOCKED`.
* **Repeated zero‑window** – a second identical ACK leaves the state at `P_WINDOW_BLOCKED`.
* **Window reopen without ACK progress** – reverse ACK with positive window but unchanged ACK results in `P_NO_PROGRESS`.
* **Window reopen with ACK progress** – positive window together with increased ACK moves to `P_PROGRESS`.
* **Forward data while retained zero‑window** – forward data segment does not clear the retained zero‑window; because `ADVERTISED_WINDOW > 0` cannot be satisfied, the machine falls to `P_UNKNOWN`.
* **Unknown window‑scale (missing SYN)** – when `WIN_SCALE` is UNKNOWN the advertised window is UNKNOWN, forcing `P_UNKNOWN`.
* **Sequence wrap‑around** – `SEQ_LT` correctly reports progress across the 2³² wrap, yielding `P_PROGRESS`.
* **Capture gap** – any `CAPTURE_GAP` makes numeric predicates UNKNOWN, causing a transition to `P_UNKNOWN` until the gap is cleared.

All scenarios produce a single deterministic next state; the precedence order
(`P_PROGRESS` → `P_WINDOW_BLOCKED` → `P_NO_PROGRESS` → `P_UNKNOWN`) resolves any
potential overlap.

### 3. Determinism conclusion

No contradictions were found.  The specification is fully deterministic under the
offline checks performed.

### 4. Remaining open issues

* The exact clearing rule for a persistent loss‑signal flag remains undefined –
  it is irrelevant for the event‑only model adopted in v1.
* Downstream tools may wish to treat a missing SYN exchange as a scale of 0
  rather than UNKNOWN; the current spec adopts the UNKNOWN convention.

---

*Prepared by the Cline coding‑assistant (offline, read‑only).*\