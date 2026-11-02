# TCP-FC-001 – Controlled TCP Receiver Flow‑Control Limitation

**Status:** **VALIDATED**

**Canonical run:** `run-005`

## Validated passive transition

```
positive receiver credit + new-data progress
    ->
zero advertised receiver window + stationary new-data high-water while a
   blocking application send() remains outstanding
    ->
positive receiver window + renewed new-data progress
```

## Evidence interpretation

The experiment validates the TCP passive‑observer transition for a controlled
receiver flow‑control limitation.  It demonstrates that a passive observer can
infer the *receiver‑flow‑control* limiting state from raw TCP window
advertisements, stationary high‑water, an outstanding blocking `send()` call,
and the subsequent reopening of credit and data progress.

**Caveat:** This does **not** imply that every TCP flow‑control episode can be
uniquely diagnosed from arbitrary passive captures; the evidence relies on the
specific controlled workload and the absence of other limiting factors such as
congestion or loss.
