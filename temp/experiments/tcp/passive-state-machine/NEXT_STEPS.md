# Next steps for the Passive TCP State‑Machine audit (audit‑001)

* **Review `FINAL_CORRECTIONS.md`** – It contains the last set of offline
  refinements: split window‑sign vs. numeric size, deterministic state‑retention,
  verified five‑event trace with reliable identifiers, and the revised semantic
  mapping (event‑only loss‑signal model).
* **Approve the corrected definitions** – Confirm the window‑scale handling
  (Section 1), the direction‑aware retention algorithm (Section 2), and the
  updated semantic mapping (Section 4).
* **Merge the approved changes** – After approval, apply the textual edits from
  `PROPOSED_REVISIONS.md` together with the additional clarifications from
  `FINAL_CORRECTIONS.md` into the authoritative `TCP-PASSIVE-STATE-MACHINE.md`.
* **Run the unit‑test suite** (if present) to verify that the spec parses and the
  state‑machine remains deterministic.
* **Decide on loss‑signal handling** – The event‑only model is recommended; if a
  persistent flag is ever required, a deterministic clearing predicate must be
  defined (see the remaining‑issues list).
* **Update the five‑event trace in the specification** – Replace the previous
  trace that used `sender_timeline.csv` with the wire‑only table from
  `FINAL_CORRECTIONS.md`.
22 | * **Create versioned specification v1** – Generate `TCP-PASSIVE-STATE-MACHINE-v1.md` incorporating all approved corrections and run the offline validation report (`validation_report_v1.md`).

These actions will finalize the specification, ensuring it is fully consistent,
deterministic, and faithful to the observable wire evidence before the frozen
state‑machine is released for reproducible passive‑TCP analysis.