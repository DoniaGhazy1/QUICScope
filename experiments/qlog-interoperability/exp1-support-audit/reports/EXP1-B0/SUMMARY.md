# EXP1-B0 — Generated qlog audit summary

Generated from files under `runs/` by `scripts/summarize_runs.py`. Do not edit generated tables manually.
Source qlogs and their original schema/event names are preserved. An absent event means **not observed**, not unsupported.

## Candidate common-workload baseline (4 MiB receive buffers)

| Stack | Run ID | Client qlog (B) | Server qlog (B) | Server sent | Client received | Missing S→C | Server loss events | Server drop events |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| quic-go | 20261110T173944Z-3540 | 285428 | 401097 | 840 | 840 | 0 | 0 | 0 |
| picoquic | 20261110T173947Z-3621 | 306878 | 365592 | 752 | 752 | 0 | 0 | 1 |
| ngtcp2 | 20261110T173950Z-3680 | 320934 | 321365 | 762 | 762 | 0 | 0 | 0 |

## Interpretation limits

- Cross-endpoint packet-number comparisons are consistency checks between endpoint logs, not an independent wire oracle.
- `packet_dropped` and `packet_lost` have different meanings.
- Event names and field semantics vary across the versions declared by the implementations.
- Socket-buffer values in metadata describe host sysctls, not verified effective socket buffer allocations.
- Reconstructed historical observations from interactive terminals belong in `TERMINAL_OBSERVATIONS.md`, not the generated CSVs.

## Other generated tables

- `run_summary.csv`: every discovered run with packet correspondence and qlog sizes.
- `qlog_files.csv`: native schemas, endpoint roles, bytes, and event totals.
- `event_counts.csv`: occurrences by exact native event name per endpoint/run.
- `field_coverage.csv`: occurrences of exact top-level data fields by event (not a semantic equivalence assertion).
