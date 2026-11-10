# Experiment 1: qlog Interoperability Support Audit

This directory contains all artifacts for Experiment 1, which audits the
availability of modern *qlog* transport observability events across three
QUIC implementations (quic-go, ngtcp2, picoquic).

The structure mirrors the plan outlined in the task description and is
intended to be reproducible.

## Directory layout
```
experiments/qlog-interoperability/exp1-support-audit/
├─ README.md                     # This file
├─ EXPERIMENT_1_REPORT.md        # Final research report
├─ versions.json                 # Implementation version metadata
├─ source_audit.csv              # Source‑code evidence matrix
├─ support_matrix.csv            # Event support matrix (source vs runtime)
├─ field_matrix.csv              # Field‑coverage matrix per event
├─ runtime_event_counts.csv     # Counts of observed events per run
├─ scripts/
│   ├─ run_audit.sh              # Build/run helper script
│   └─ analyze_qlog.py           # Simple qlog parser
└─ runs/
    ├─ quic-go/
    ├─ ngtcp2/
    └─ picoquic/
```

All files are initially empty placeholders and will be populated by the
automation steps.
