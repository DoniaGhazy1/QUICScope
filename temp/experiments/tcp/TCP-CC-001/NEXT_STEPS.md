# Next Steps – TCP‑CC‑001

**Current research objective**
> Derive a robust, reproducible classification of the congestion‑control algorithm used by the
> remote endpoint (VM 2) based on the kernel‑level TCP observations collected by the filtered
> `tcp_write_xmit` probe.

---

## 1. Last successfully completed task
* Offline validation of the successful smoke‑test run `smoke-1791488316-YJK6` (see `VALIDATION.md`).
* Full classifier audit – independent recomputation of the D/F/C/R predicates for all 165,756 BPF observations (`analysis/audit/audit_classifier.py`) found **zero mismatches**, confirming the classifier’s correctness across the entire dataset.
* All raw artefacts have been preserved; documentation files (`EXPERIMENT_LOG.md`, `NETWORK_SETUP.md`, `INSTRUMENTATION.md`, `NEXT_STEPS.md`) have been created.

---

## 2. Validated evidence available
| Artifact | Description | Path |
|----------|-------------|------|
| Network configuration (post‑correction) | VM 1 and VM 2 IP/route/ARP status | `/home/rosa/experiments/tcp/TCP-CC-001/NETWORK_SETUP.md` |
| BPF probe script | Filtered `tcp_write_xmit` probe | `/home/rosa/experiments/tcp/TCP-CC-001/monitor/smoke-001/tcp_write_xmit_filtered.bt` |
| Successful run artefacts | Application logs, TCP_INFO, BPF events, clock offsets | `/home/rosa/experiments/tcp/TCP-CC-001/monitor/smoke-1791488316-YJK6/` |
| Validation analysis | Offline consistency checks and numeric summary | `/home/rosa/experiments/tcp/TCP-CC-001/monitor/smoke-1791488316-YJK6/VALIDATION.md` |

---

## 3. Unresolved questions / open issues
* **Semantic mapping** – How do the observed `ca_state` transitions and congestion‑window dynamics map
  to known congestion‑control algorithms (e.g., CUBIC, BBR, Reno)?
* **Loss detection** – The BPF log shows `lost_out` values; we need to confirm whether these correspond to
  genuine packet loss on the network or to kernel‑side retransmission handling.
 * **Sampling granularity** – `sender_tcpinfo_log.csv` provides **2 848** samples over **≈ 3 s**,
   yielding an average interval of **≈ 1.05 ms** per sample.  This is coarser than the previously
   reported ~73 µs and may miss rapid state transitions for some congestion‑control algorithms.
   Further evaluation is needed to determine whether finer sampling (e.g., decreasing the probe interval)
   improves classification accuracy.
 * **Clock‑offset drift** – The pre‑run and post‑run offset measurements differ by **2 274 ns**,
   exceeding the individual uncertainties (± 407 ns and ± 305 ns).  This indicates a small monotonic‑raw
   clock drift (~0.76 ppm) over the experiment duration.  While the drift is modest, it should be accounted
   for when aligning timestamps across the BPF, TCP_INFO, and application logs.

* **Offline semantic evidence analysis** – The `analysis/semantic_correlation.py` script has been
  executed, producing a merged event table and a concise evidence summary (`SEMANTIC_EVIDENCE.md`).
  These artefacts provide a documented mapping from raw measurements to the four semantic predicates
  (D, F, C, R) and identify remaining uncertainties.  The next research phase can now build a classifier
  on top of this validated evidence.
* **Event‑loss detection** – The probe buffer size was not tuned; while no loss warnings appeared, we have
  no guarantee that overflow did not occur at peak traffic.
* **Provisional predicate counts** – The counts in `semantic_summary.txt` are provisional due to earlier exact‑timestamp matching limitations; they will be revisited after refining the merging approach.

---

## 4. Recommended next action (to be performed after approval)
1. **Correlation script** – Write a Python/Julia analysis script that joins the three data streams
   (application log, TCP_INFO, BPF events) on the common `timestamp_ns` axis and visualises the evolution
   of `snd_cwnd`, `ca_state`, and loss counters.
2. **Ground‑truth runs** – Execute controlled experiments where the receiver’s congestion‑control
   algorithm is known (e.g., force CUBIC, BBR) and record the same artefacts.  This will provide a training set
   for classification.
3. **Buffer‑size assessment** – Measure the BPF per‑CPU buffer usage during a heavy‑load run to ensure that
   no events are silently dropped.
4. **Documentation update** – Extend `EXPERIMENT_LOG.md` with the outcomes of the above steps.

---

## 5. Actions that **must not** be taken without explicit approval
* Modifying any **network configuration** on either VM (IP addresses, routes, firewall rules).
* Running the **sender** binary (`sender_new`) or any other traffic‑generating tool outside the controlled
  smoke‑test harness.
* Changing the **BPF probe script** (filter constants, attached kprobe) – any modification should be
  version‑controlled and documented.
* Deleting or overwriting any raw artefact files (CSV, log, clock‑offset files).  New files may be added
  but existing data must remain untouched.

---

### Documentation workflow reminder
The **Documentation Rules** (see the project description) must be followed for every future task:
1. Inspect existing documentation and frozen evidence.
2. Perform only the authorized work.
3. Save results immediately to the appropriate persistent file.
4. Record failures as carefully as successes.
5. Update `EXPERIMENT_LOG.md` and `NEXT_STEPS.md`.
6. Include exact artifact paths in the final report.
7. Clearly separate measurements from interpretations.
8. Never overwrite frozen experimental evidence.
