# Final Offline Verification Report – TCP‑CC‑001

This document assembles the ten‑item summary of the complete offline verification of the
endpoint‑proxy classifier.  All artefacts are stored under the experiment directory
`/home/rosa/experiments/tcp/TCP-CC-001/`.

1. **Data availability**
   * Event‑centered TSV – raw BPF observations:
     `/home/rosa/experiments/tcp/TCP-CC-001/analysis/event_centered_output/event_centered.tsv`
   * Joint predicates TSV – stored classifier output:
     `/home/rosa/experiments/tcp/TCP-CC-001/analysis/state_combination_output/joint_predicates.tsv`

2. **Audit script**
   * `analysis/audit/audit_classifier.py` – recomputes D/F/C/R for every BPF row and
     validates the stored predicates.

3. **Audit summary**
   * `analysis/audit/audit_summary.txt` – contains total rows, missing raw rows, and
     predicate mismatch count (zero mismatches).

4. **Predicate mismatches file** (empty)
   * `analysis/audit/predicate_mismatches.tsv`

5. **State distribution**
   * `analysis/audit/state_distribution.txt` – counts of each derived semantic state.

6. **Transition counts**
   * `analysis/audit/transition_counts.tsv` – observed state‑to‑state transition frequencies.

7. **Example transitions**
   * `analysis/audit/example_transitions.tsv` – first three examples of the two
     key transitions (READY→FC_LIMITED and READY→CC_LIMITED).

8. **Full audit report**
   * `analysis/FULL_CLASSIFIER_AUDIT.md` – detailed methodology, results, and conclusions.

9. **Updated semantic evidence**
   * `analysis/SEMANTIC_EVIDENCE.md` – corrected D predicate formula, inclusion of the
     full‑offline verification note, and explicit statement that no `MULTIPLE_LIMITED`
     observations were detected.

10. **Probe‑placement clarification**
    * `INSTRUMENTATION.md` – new *3.1 Probe placement semantics* subsection confirming that
      the `kprobe:tcp_write_xmit` fires on function entry, i.e., before congestion‑window or
      flow‑control checks, and therefore captures the kernel state prior to early‑exit
      decisions.

All files listed above are present in the repository and have been verified to contain the
expected content.  The audit confirms that the classifier’s predicate computation is correct
for the entire dataset, and that the semantic state mapping is consistent with the observed
kernel behaviour.
