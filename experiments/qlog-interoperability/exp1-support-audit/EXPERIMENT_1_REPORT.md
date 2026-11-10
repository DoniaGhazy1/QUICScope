# Experiment 1 Report

## Research Question
**RQ1:** *To what extent do heterogeneous QUIC implementations support and expose the transport observability events defined by modern qlog specifications?*

## Scope
The audit covers three QUIC implementations:
1. **quic-go** – Go implementation, includes built‑in qlog support.
2. **ngtcp2** – C library, does **not** provide native qlog output.
3. **picoquic** – C library, does **not** provide native qlog output.

## Version Metadata
The exact source revisions used are listed in `versions.json`.

## Source‑Code Evidence (`source_audit.csv`)
The CSV records whether each target event is defined in the source tree.  
All three blocking‑state events are **implemented** only in **quic-go**; the other two stacks have no qlog code for these events.

## Runtime Observation (`runtime_event_counts.csv`)
Baseline transfers were executed using the `run_audit.sh` script.  
Only **quic-go** produced a qlog trace (`client.sqlog`). No `connection_data_blocked_updated`, `stream_data_blocked_updated`, or `datagram_data_blocked_updated` events were observed during the simple echo transfer, so counts are zero.  
`ngtcp2` and `picoquic` have no qlog output (placeholder files created).

## Field Coverage (`field_matrix.csv`)
For **quic-go**, the required fields (`old`, `new`, `reason`) exist in the source definitions. The other implementations have no fields because the events are absent.

## Interpretation
* **Implementation support:** Only quic‑go defines the modern blocking‑state events.  
* **Runtime emission:** In a basic echo workload the events are not triggered, which is expected because no flow‑control or congestion limiting occurs.  
* **Missing qlog in ngtcp2/picoquic:** These stacks would need additional instrumentation to emit comparable events; they currently expose no qlog trace.

## Limitations
* The baseline workload is minimal and does not provoke congestion, flow‑control, or application‑limited states; therefore the blocking events remain untriggered.  
* ngtcp2 and picoquic were built without any qlog extensions; deeper instrumentation would be required for a fair comparison.

## Implications for Further Experiments
* The presence of the event schema in **quic‑go** suggests that the qlog specification can represent the desired diagnostics, but actual usage depends on workload conditions.  
* To evaluate the diagnostic completeness across implementations, future experiments must (a) generate conditions that cause blocking, and (b) add or enable qlog‑style logging in ngtcp2/picoquic (e.g., via custom eBPF probes or library patches).

*This report documents the current state of qlog event support for Experiment 1. Subsequent experiments can build on these findings to explore deeper transport‑level observability.* 
