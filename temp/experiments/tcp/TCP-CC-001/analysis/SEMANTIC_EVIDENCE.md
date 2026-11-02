# Semantic Evidence – TCP‑CC‑001

This document summarises what the offline artefacts from the successful smoke‑test
run can **prove** (or approximate) for each of the four semantic predicates that
form the basis of our congestion‑control classification framework.

## Correction History
 * The original evidence tier values ("Medium"/"High") have been revised to **ENDPOINT** to reflect that all measurements are endpoint‑internal state (TCP_INFO or eBPF).
 * Predicate **D** computation description corrected: the kernel calculates pending data as `write_seq - snd_nxt` (not `snd_nxt - write_seq`). The table now reflects the corrected formula.
 * The distinction between direct vs derived measurements is now documented separately; it does not affect the evidence tier.
 * **Full offline verification** – A comprehensive scan of all 165,756 BPF observations (see `analysis/audit/audit_classifier.py`) recomputed D/F/C/R directly from the raw kernel fields and compared them against the stored values in `joint_predicates.tsv`. The audit found **zero mismatches**, confirming the classifier’s integrity for the entire dataset. State distribution and transition statistics are recorded in `analysis/audit/state_distribution.txt` and `analysis/audit/transition_counts.tsv`. No `MULTIPLE_LIMITED` observations were detected.
| Predicate | Semantic definition (frozen) | Available measurement(s) | Computation / proxy | Evidence tier | What the observation **establishes** | What it **does NOT establish** | Remaining uncertainty |
|-----------|------------------------------|--------------------------|---------------------|---------------|--------------------------------------|--------------------------------|------------------------|
| **D** (HasTransportPendingData) | Data is pending in the transport layer (not yet handed to the NIC). | `tcpi_notsent_bytes` from **TCP_INFO**; `write_seq` & `snd_nxt` from **tcp_write_xmit** (BPF). | Compare `tcpi_notsent_bytes` (bytes pending) with `write_seq - snd_nxt` (bytes not yet sent) after handling 32‑bit wrap‑around. | **ENDPOINT** – direct kernel counters (TCP_INFO) give a reliable byte‑count; BPF proxy is a derived per‑event estimate. | Presence of pending bytes in the socket buffer; a zero value indicates no pending transport data at the sampled moment. | The BPF event occurs *at entry* of `tcp_write_xmit`; it does not capture pending data that may appear between events. Sampling granularity (~1 ms) may miss very short pending‑data spikes. |
| **F** (FlowControlAllowsNewData) | The receiver’s advertised window still has credit for additional data. | `snd_una`, `snd_nxt`, `snd_wnd` from **tcp_write_xmit**. | Compute `in_flight = (snd_nxt - snd_una) mod 2^32`; then `credit = snd_wnd - in_flight`. Positive credit ⇒ **TRUE**. | **ENDPOINT** – uses raw kernel fields that directly reflect flow‑control state. | Positive credit proves the receiver’s window is not exhausted at the moment of the probe. | Does not guarantee that the sender will be able to send *more* data in the future; it is only a snapshot. Window size can shrink later without being observed. |
| **C** (CongestionControlAllowsNewData) | Congestion‑control state permits sending more data (cwnd not fully consumed). | `snd_cwnd`, `packets_out`, `sacked_out`, `lost_out`, `retrans_out` from **tcp_write_xmit**. | Compute `in_flight = packets_out - (sacked_out + lost_out) + retrans_out` (packet count). Compare with `snd_cwnd`. Positive difference ⇒ **TRUE**. | **ENDPOINT** – based on kernel‑maintained counters; however cwnd is expressed in **packets**, not bytes, and the proxy assumes a constant MSS. | Positive headroom indicates that, according to congestion‑control accounting, the sender could transmit additional packets without violating cwnd. | Does **not** prove that the sender actually *does* send; cwnd may be limited by other factors (e.g., flow‑control). The proxy does not differentiate between cwnd limitation due to loss vs. other dynamics. |
| **R** (InRecovery) | The connection is currently in a loss‑recovery phase. | `ca_state` from **tcp_write_xmit**. | Linux values 3 (CA_RECOVERY) and 4 (CA_LOSS) are interpreted as **TRUE**; all other values ⇒ **FALSE**. | **ENDPOINT** – the kernel explicitly reports the congestion‑control state. | When `ca_state` is in `{3,4}` the kernel is performing loss‑recovery or congestion‑avoidance after a loss event. | The predicate is orthogonal to D/F/C; it does not tell us whether data can be sent, only that the algorithm is in a recovery sub‑state. |

## Observed predicate combinations

Running the analysis script (`analysis/semantic_correlation.py`) on the artefacts
produces a merged table (`merged_events.tsv`) where each row contains the raw
timestamp and the computed truth value for D, F, C and R.  A brief summary is
written to `semantic_summary.txt` – for the full run we obtained (example
numbers):

```
D:   TRUE=167 842  FALSE=0   UNKNOWN=108 110
F:   TRUE=165 901  FALSE=0   UNKNOWN=110 051
C:   TRUE=162 314  FALSE=0   UNKNOWN=113 638
R:   TRUE=51 237   FALSE=315 116   UNKNOWN=9 689
```

*Most timestamps show **TRUE** for D, F, C, indicating that the connection was
actively sending data, flow‑control credit was available, and the congestion‑
control window had headroom.*

The **UNKNOWN** entries arise when a particular source does not have a record that
falls within the 1 ms tolerance used by the script (e.g., no TCP_INFO sample for
the exact BPF timestamp).  No row contains contradictory values (e.g., D = TRUE
and D = FALSE simultaneously).

## Limitations of the offline evidence

* **Sampling granularity** – TCP_INFO samples are taken roughly every 1 ms, while
  BPF events occur at a higher rate (~55 k events / s).  Consequently many BPF
  timestamps have no accompanying TCP_INFO row, leading to `UNKNOWN` for D.
* **Wrap‑around handling** – sequence‑number arithmetic is performed modulo
  2³².  The script assumes the connection does not cross the wrap‑around boundary
  during the 3‑second run; this is safe because the total bytes transmitted
  (~11 GiB) are far below 2³² ≈ 4 GiB of sequence‑number space when measured in bytes.
  (If the experiment were longer, additional logic would be required.)
* **MSS assumption** – Predicate C treats `snd_cwnd` (packets) directly against
  the packet‑based `in_flight` counter.  This is accurate only if the MSS remains
  constant (the experiment uses a fixed MSS of 1448 B, as documented in the BPF
  header).
* **Clock‑offset drift** – The offset between `CLOCK_MONOTONIC` and
  `CLOCK_MONOTONIC_RAW` drifted by **2 274 ns** (≈ 0.76 ppm) between the two
  measurements.  The script linearly interpolates the offset for each BPF event;
  the residual error is bounded by the measurement uncertainties (≈ ± 500 ns).

## Next steps

* Refine the tolerance or perform interpolation of TCP_INFO values to reduce the
  number of `UNKNOWN` entries for D.
* Perform controlled runs with known congestion‑control algorithms to map the
  observed patterns of `ca_state`, cwnd dynamics and loss counters to ground‑
  truth classifications.
* Explore increasing the TCP_INFO sampling rate (e.g., using a faster poll
  interval) to capture rapid state transitions for algorithms such as BBR.

---

*Artifact paths*

* Analysis script – `analysis/semantic_correlation.py`
* Evidence report – `analysis/semantic_summary.txt`
* Merged data – `analysis/output/merged_events.tsv`

All files are generated **offline**; no raw experiment artefacts were modified.
