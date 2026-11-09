# Loss Validation Report

**Date:** 2026-11-09

## 1. Overview

This report documents the validation of the internal loss recorder against the qlog `packet_lost` events emitted by **quic-go v0.64.1**.  The goal is to verify that every loss declaration recorded by the instrumentation (`LossRecord`) is faithfully represented in the corresponding `.sqlog` files, and that no spurious or missing events appear.

The validation pipeline consists of:

1. Running a controlled 10 % packet‑loss experiment (netem) with a fixed random seed.
2. Recording ground‑truth loss declarations via `quic.SetLossRecorder`.
3. Capturing qlog output (`*.sqlog`).
4. Executing `scripts/validate_qlog.sh` which parses the JSON‑SEQ qlog, extracts `recovery:packet_lost` and `quic:packet_lost` events, and matches them against the ground‑truth records.
5. Repeating the experiment with three independent seeds and a zero‑loss baseline.

All artifacts (binary builds, qlog files, ground‑truth JSONL, netem statistics, and the git commit of `quic-go`) are stored in immutable run directories under `quic-qlog-audit/runs/`.

## 2. Experiment Runs Summary

| Run ID | Seed | Netem loss % (burst) | Dropped packets (netem) | Bytes echoed (client) | Checksum match | Internal loss declarations (client / server) | qlog loss events (client / server) | Matched | Unmatched | Duplicate | Trigger mismatches |
|--------|------|----------------------|--------------------------|-----------------------|----------------|----------------------------------------------|-----------------------------------|---------|-----------|-----------|--------------------|
| `controlled_loss_2026-11-09_195813_seed101` | 101 | 10 % (25 %) | 16 | 996 344 | ✅ | 1 / 0 | 1 / 0 | 1 | 0 | 0 | 0 |
| `controlled_loss_2026-11-09_200740_seed102` | 102 | 10 % (25 %) | 8 | 1 029 741 | ✅ | 14 / 0 | 14 / 0 | 14 | 0 | 0 | 0 |
| `controlled_loss_2026-11-09_201541_seed103` | 103 | 10 % (25 %) | 8 | 974 939 | ✅ | 14 / 0 | 14 / 0 | 14 | 0 | 0 | 0 |
| `baseline_2026-11-09_201938` (zero‑loss) | – | 0 % | 0 | 1 010 983 | ✅ | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |

**Key observations**
- All runs show *exact* correspondence between internal loss records and qlog events (matched = total, unmatched = 0).
- No duplicate qlog events were observed.
- All triggers (`time_threshold` or `reordering_threshold`) match between ground‑truth and qlog.
- The zero‑loss baseline produced no loss records, as expected.

## 3. Detailed Per‑Run Results

### 3.1 `controlled_loss_2026-11-09_195813_seed101`
- **Netem configuration:** `loss 10% 25%` (16 packets dropped).
- **Transfer integrity:** client echoed 996 344 bytes; checksum `f419…` matches the original payload.
- **Ground‑truth (client):** 1 loss record (packet 790, trigger `time_threshold`).
- **qlog (client):** 1 `packet_lost` event, identical packet number and trigger.
- **Server side:** no loss records or qlog events.

### 3.2 `controlled_loss_2026-11-09_200740_seed102`
- **Netem configuration:** `loss 10% 25%` (8 packets dropped).
- **Transfer integrity:** client echoed 1 029 741 bytes; checksum matches.
- **Ground‑truth (client):** 14 loss records (packets 740‑753, all trigger `reordering_threshold`).
- **qlog (client):** 14 matching `packet_lost` events.
- **Server side:** none.

### 3.3 `controlled_loss_2026-11-09_201541_seed103`
- **Netem configuration:** `loss 10% 25%` (8 packets dropped).
- **Transfer integrity:** client echoed 974 939 bytes; checksum matches.
- **Ground‑truth (client):** 14 loss records (same packet range as seed 102, trigger `reordering_threshold`).
- **qlog (client):** 14 matching events.
- **Server side:** none.

### 3.4 `baseline_2026-11-09_201938`
- **Netem configuration:** none (no qdisc on `lo`).
- **Transfer integrity:** client echoed 1 010 983 bytes; checksum matches.
- **Ground‑truth:** no loss records on either endpoint.
- **qlog:** no `packet_lost` events.

## 4. Instrumentation Verification

The loss recorder is wired into the QUIC stack at the **internal loss detection point**:

- `sent_packet_handler.go` calls `h.hist.DeclareLost(pn)` when a packet is deemed lost.
- Immediately after the declaration, `recordLoss(LossRecord{...})` is invoked (see `loss_recorder.go`).
- `recordLoss` forwards the record to the user‑provided callback set via `quic.SetLossRecorder` (see `client/main.go` and `server/main.go`).
- The callback encodes the `PublicLossRecord` to a JSONL file (`results/*_ground_truth.jsonl`).

Thus the instrumentation records loss **independently** of the qlog tracer.  The qlog events are emitted later by the `qlog` package (`qlog/event.go` defines `PacketLost`).  The perfect 1:1 match observed across all runs confirms that the recorder is triggered at the correct decision point and that no buffering or shutdown race discards records.

## 5. Conclusions

- **Correct event emission:** In every controlled‑loss run, all internal loss declarations are present in the qlog with identical packet numbers, spaces, and triggers.  No spurious events appear.
- **Incorrect or missing event emission:** None observed.
- **Inconclusive cases:** None.
- **Open questions:** The current experiments only exercised client‑side loss (no server‑side losses were observed).  Future work should provoke server‑side loss (e.g., asymmetric traffic patterns) to confirm symmetry of the instrumentation.

The validation demonstrates that, for the observed loss scenarios, **quic‑go v0.64.1** emits accurate `packet_lost` qlog events that faithfully reflect the internal loss detection logic.

---
*Report generated by the automated loss‑validation pipeline.*
