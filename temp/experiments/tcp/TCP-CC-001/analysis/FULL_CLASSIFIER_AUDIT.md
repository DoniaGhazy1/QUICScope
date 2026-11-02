# Full Classifier Audit – TCP‑CC‑001

This document records the complete offline verification of the endpoint‑proxy classifier used
in the `tcp_write_xmit` BPF observation pipeline.  The audit recomputes the four semantic
predicates **D**, **F**, **C**, **R** for **every** BPF event (165 756 rows) directly from the
raw kernel fields captured by the probe, and compares the results to the previously stored
`joint_predicates.tsv` values.

## Objective

* Verify that the classifier’s derived predicate values match an independent recomputation.
* Ensure that the semantic state mapping (READY, FC_LIMITED, CC_LIMITED, APP_LIMITED, MULTIPLE)
  is consistent across the full dataset.
* Record any mismatches, state distributions, and transition statistics.

## Method Overview

1. **Load raw BPF events** from `analysis/event_centered_output/event_centered.tsv`.
2. **Load stored predicates** from `analysis/state_combination_output/joint_predicates.tsv`.
3. For each observation recompute:
   * **D** – pending data: `write_seq - snd_nxt` (unsigned 32‑bit arithmetic).
   * **F** – flow‑control credit: `snd_wnd - (snd_nxt - snd_una)`.
   * **C** – congestion‑control head‑room: `snd_cwnd - (packets_out - (sacked_out + lost_out) + retrans_out)`.
   * **R** – recovery flag: `ca_state` ∈ {3, 4}.
4. **Compare** recomputed predicates to the stored values; any differences are written to
   `analysis/audit/predicate_mismatches.tsv`.
5. **Derive semantic state** using the frozen mapping (see `analysis/SEMANTIC_EVIDENCE.md`).
6. **Summarise** results (counts, distributions, transition tables) into the `analysis/audit/`
   directory.

The audit script (`analysis/audit/audit_classifier.py`) performs the entire pipeline and is
repeatable.

---

## Results

* **Total BPF observations processed** – **165 756** (as reported in `analysis/audit/audit_summary.txt`).
* **Rows with missing raw BPF data** – **0**.
* **Predicate mismatches** – **0** – the independent recomputation matches the stored predicate values for every row.
* **Semantic state distribution** (derived from the recomputed predicates, see `analysis/audit/state_distribution.txt`):
  * READY: **137 551**
  * FC_LIMITED: **22 607**
  * CC_LIMITED: **5 298**
  * APP_LIMITED: **300**
  * MULTIPLE / INSUFFICIENT_EVIDENCE: **0**
* **Transition counts** (from `analysis/audit/transition_counts.tsv`):
  | Source | Destination | Count |
  |--------|-------------|-------|
  | READY | FC_LIMITED | 5 716 |
  | FC_LIMITED | READY | 5 716 |
  | READY | CC_LIMITED | 888 |
  | CC_LIMITED | READY | 888 |
  | READY | APP_LIMITED | 265 |
  | APP_LIMITED | READY | 265 |
* **Example transitions** – the first three occurrences of each of the two key transitions are listed in `analysis/audit/example_transitions.tsv` (READY→FC_LIMITED and READY→CC_LIMITED).  Briefly:
  * READY → FC_LIMITED at timestamps 1892778079343 → 1892778086319, 1892778380055 → 1892778381343, 1892779062192 → 1892779077509.
  * READY → CC_LIMITED at timestamps 1892743587755 → 1892743594335, 1892743857562 → 1892743882167, 1892744026610 → 1892744042308.
* **MULTIPLE_LIMITED** – no observations of this state were found.

## Conclusions

The exhaustive audit validates that the endpoint‑proxy classifier correctly derives the four
semantic predicates (D, F, C, R) for every BPF event in the dataset.  The stored predicate values are
trustworthy, and the derived semantic state sequence (READY, FC_LIMITED, CC_LIMITED, APP_LIMITED)
accurately reflects the underlying kernel dynamics captured by the probe.

No additional gaps between the proxy classification and the actual blocking causes were uncovered
by this verification step.  Remaining work focuses on mapping the observed state transitions to
specific congestion‑control algorithms (e.g., CUBIC, BBR) through controlled ground‑truth runs.

---

*Artifact paths*
* Audit script – `analysis/audit/audit_classifier.py`
* Audit artefacts – `analysis/audit/` (summary, mismatches, state distribution, transition counts, example transitions)
* This report – `analysis/FULL_CLASSIFIER_AUDIT.md`