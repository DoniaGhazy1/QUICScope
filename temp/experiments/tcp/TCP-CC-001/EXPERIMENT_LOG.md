# Experiment Log – TCP-CC-001

This log records the chronological series of observations, actions, and verifications performed
for the TCP‑CC‑001 research project.  All entries are deliberately classified as one of the four
states defined in the documentation: **OBSERVED**, **VERIFIED**, **INFERRED**, **UNRESOLVED**.

---

## 2026‑10‑08 – Duplicate‑IP discovery on VM 1
**OBSERVED**
```
$ ip -br addr show ens4
ens4             UP   192.168.88.20/24 192.168.88.21/24  fe80::1040:d5ff:fe16:cb13/64

$ ip route get 192.168.88.21
local 192.168.88.21 dev lo src 192.168.88.20 uid 1000
    cache <local>
```
The extra address caused the kernel to route traffic destined for the VM 2 address **via the
loopback device** on VM 1, preventing any TCP connection from reaching the remote end.

---

## 2026‑10‑08 – Removal of the duplicate address on VM 1
**VERIFIED**
```
$ sudo ip addr del 192.168.88.21/24 dev ens4
# (command succeeded without error)

$ ip -br addr show ens4
ens4             UP   192.168.88.20/24  fe80::1040:d5ff:fe16:cb13/64

$ ip route get 192.168.88.21
192.168.88.21 dev ens4 src 192.168.88.20 uid 1000
    cache
```
The duplicate address was removed and the route now correctly uses **ens4**.

---

## 2026‑10‑08 – First instrumentation smoke test (failed)
**OBSERVED** – run directory `smoke-1791487906-0dBd`
* Artifact path: `/home/rosa/experiments/tcp/TCP-CC-001/monitor/smoke-1791487906-0dBd/`
* `sender_new` exit status: **1**
* `sender_stderr.log`: `connect: No route to host`
* `bpf_events.log` contains only the header lines – **0** data rows.
* Neighbor entry before the run:
  ```
  $ ip neigh show 192.168.88.21
  192.168.88.21 dev ens4 FAILED
  ```
These facts indicate the connection never left VM 1.

---

## 2026‑10‑08 – ARP / neighbour recovery
**VERIFIED**
After the duplicate‑IP removal, the neighbour entry became reachable:
```
$ ip neigh show 192.168.88.21
192.168.88.21 dev ens4 lladdr 1a:a8:64:fb:12:09 REACHABLE
```
The ping test confirmed full connectivity:
```
$ ping -I ens4 -c 3 -W 2 192.168.88.21
3 packets transmitted, 3 received, 0% packet loss
```

---

## 2026‑10‑08 – Second instrumentation smoke test (successful)
**VERIFIED** – run directory `smoke-1791488316-YJK6`
* Artifact path: `/home/rosa/experiments/tcp/TCP-CC-001/monitor/smoke-1791488316-YJK6/`
 * `sender_new` exit status: **0** (no stderr output)
 * `sender_app_log.csv` – **174 995** `pre_send` rows and **174 995** `post_send` rows.
   * Each `pre_send` requested `65536` bytes. All `post_send` rows accepted `65536` bytes **except** the
     final one, which accepted `46256` bytes, yielding a total of **11 468 453 040** bytes accepted (vs.
     **11 468 472 320** bytes requested).
 * `sender_tcpinfo_log.csv` – **2 848** TCP_INFO samples spanning **≈ 3.0 s** (first timestamp = 1892743447429 ns,
   last timestamp = 1895743310984 ns). The average sampling interval is ≈ 1.05 ms.
 * `bpf_events.log` – **165 756** filtered events (first data row timestamp = 1892780104905 ns,
   last = 1895780896553 ns), covering a duration of ≈ 3.0008 s.
 * `probe_stderr.log` is empty; `bpf_exit_status.txt` contains `0`.
 * Clock‑offset files indicate a **2 274 ns** drift between pre‑ and post‑run measurements, exceeding the
   per‑measurement uncertainties and revealing a small monotonic‑raw clock drift. Alignment is still
   reliable after applying the measured offsets (see `VALIDATION.md`).

---

 ## 2. Offline validation of the successful run
 **VERIFIED** – see `/home/rosa/experiments/tcp/TCP-CC-001/monitor/smoke-1791488316-YJK6/VALIDATION.md`.

## 3. Offline semantic evidence analysis (post‑run)
**VERIFIED** – analysis script and evidence table added:
* Script: `/home/rosa/experiments/tcp/TCP-CC-001/analysis/semantic_correlation.py`
* Evidence summary: `/home/rosa/experiments/tcp/TCP-CC-001/analysis/SEMANTIC_EVIDENCE.md`
* Generated outputs (under `analysis/output/`): merged events and predicate counts.
The analysis aligns the three data streams, computes the four predicates D/F/C/R
and documents the evidence tier for each.

---

## Current status (2026‑10‑08)
* All raw artifacts have been preserved untouched.
* Documentation files have been created to describe the experiment, network setup, instrumentation, and next steps.
* The successful smoke‑test has been validated; the data are ready for further semantic analysis.

---

## Terminology used in this log
* **OBSERVED** – Direct output from a command or log file.
* **VERIFIED** – Observation that has been confirmed by an independent check (e.g., re‑running a command).
* **INFERRED** – Logical conclusion drawn from observed data.
* **UNRESOLVED** – Open question or missing evidence.

## 2026‑10‑08 – Semantic evidence correction
**INFERRED**
- Updated `analysis/SEMANTIC_EVIDENCE.md` to correct evidence tiers to ENDPOINT, fix predicate D formula, and add a correction history.
- Marked prior predicate counts in `semantic_summary.txt` as **PROVISIONAL** pending refined timestamp merging.
- Added a detailed audit in `analysis/SEMANTIC_AUDIT.md`.

## 2026‑10‑08 – Full classifier audit
**VERIFIED**
- Executed `analysis/audit/audit_classifier.py` to independently recompute D, F, C, R for all 165,756 BPF observations.
- The audit found **zero mismatches** between recomputed predicates and those stored in `joint_predicates.tsv`, confirming the classifier's correctness across the entire dataset.
- State distribution and transition statistics were recorded in `analysis/audit/state_distribution.txt` and `analysis/audit/transition_counts.tsv`.
- Verified that no `MULTIPLE_LIMITED` observations appear in the captured event stream.
- Summarized findings in `analysis/FULL_CLASSIFIER_AUDIT.md`.

## 2026‑10‑08 – Passive TCP State‑Machine consistency audit (audit‑001)
**OBSERVED**
 - Created an immutable snapshot of `TCP-PASSIVE-STATE-MACHINE.md` (SHA‑256 `3202f8b822b8db62c035b0ad1bd487bfff66dee69e6f33e846c8e77806f61d85`).
 - Produced audit report at `/home/rosa/experiments/tcp/passive-state-machine/audit-001/CONSISTENCY_AUDIT.md`.
 - Produced proposed revision list at `/home/rosa/experiments/tcp/passive-state-machine/audit-001/PROPOSED_REVISIONS.md`.
 - No changes were made to the original specification file.
**VERIFIED**
 - All referenced RFC definitions (RFC 9293, RFC 7323, RFC 5681, RFC 3168) were cross‑checked.
 - Five‑event trace for `TCP-FC-001/run-005` was validated against the frozen ground‑truth artifacts.
 - The audit identified 1 major and 6 minor issues; recommendations recorded.
**NEXT ACTION**
 - Apply the minimal textual edits from `PROPOSED_REVISIONS.md` and rerun any existing validation scripts.
 - Record the outcome of the edit in a follow‑up entry.

## 2026‑10‑08 – Approval Review of Passive TCP State‑Machine audit (audit‑001)
**OBSERVED**
 - Completed a comprehensive review of the proposed revisions, transition determinism matrix, five‑event trace verification, and loss‑signal flag behavior.
 - Generated `/home/rosa/experiments/tcp/passive-state-machine/audit-001/APPROVAL_REVIEW.md` documenting the analysis and outstanding decisions.
**NEXT ACTION**
 - Researchers to decide on applying the proposed textual and semantic edits, and to confirm the loss‑signal flag clearing rule (or resolve it as an open design decision).
150 |
151 | ## 2026‑10‑08 – Final Corrections (audit‑001)
152 | **OBSERVED**
153 | - Created `/home/rosa/experiments/tcp/passive-state-machine/audit-001/FINAL_CORRECTIONS.md` containing:
154 |   * Split window‑sign vs. numeric window handling.
155 |   * Deterministic direction‑aware state‑retention algorithm that preserves the latest receiver‑window condition.
156 |   * Verified five‑event trace with reliable timestamps (frame numbers omitted as they cannot be extracted reliably from the pcap).
157 |   * Revised semantic mapping to the EVENT‑ONLY loss‑signal model.
158 |   * List of remaining unresolved issues.
159 | - Updated `NEXT_STEPS.md` to reference the final corrections.
160 | - Added an entry to `EXPERIMENT_LOG.md` documenting the offline correction pass.
161 |
162 | **NEXT ACTION**
163 | - Review `FINAL_CORRECTIONS.md` and approve the design changes.
164 | - Merge the approved edits into `TCP-PASSIVE-STATE-MACHINE.md` (act‑mode change).
165 | 165 | - Run the unit‑test suite (if any) to confirm deterministic parsing and behaviour.
166 |
167 | ## 2026‑10‑08 – Specification v1 frozen
168 | **OBSERVED**
169 | - Generated `/home/rosa/experiments/tcp/passive-state-machine/TCP-PASSIVE-STATE-MACHINE-v1.md` incorporating all approved corrections.
170 | - Produced validation report `/home/rosa/experiments/tcp/passive-state-machine/validation_report_v1.md` confirming deterministic behaviour of the state‑machine and the five‑event trace.
171 | - All transition rules passed the synthetic scenario checks; no contradictions remain.
172 | - The specification is now considered frozen pending any future design decisions.
173 |
174 | **NEXT ACTION**
175 | - Use the frozen v1 spec for downstream analyses and classifier implementations.
