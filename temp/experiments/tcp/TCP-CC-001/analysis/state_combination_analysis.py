#!/usr/bin/env python3
"""state_combination_analysis.py – Derive semantic states from BPF events.

This script works **only** on the already‑generated ``event_centered.tsv`` file
found in ``analysis/event_centered_output``.  It validates the BPF predicate
counts, classifies each BPF observation into the frozen semantic states, and
produces a suite of artefacts under ``analysis/state_combination_output``:

* ``joint_predicates.tsv`` – per‑BPF‑event joint predicate values plus the
  derived semantic state.
* ``semantic_state_counts.txt`` – counts of each defined state (READY, APP_LIMITED,
  FC_LIMITED, CC_LIMITED, MULTIPLE) and any unsupported combinations.
* ``observed_transitions.tsv`` – consecutive state transitions sorted by the
  original (raw) timestamp.
* ``transition_summary.txt`` – most frequent transition pairs and concrete
  examples for the requested scenarios.
* ``STATE_COMBINATION_ANALYSIS.md`` – a human‑readable report.

The script does **not** modify any existing files; it only reads the generated
event‑centered data and writes new outputs.
"""

from __future__ import annotations

import csv
import pathlib
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Mapping from D/F/C boolean triple to the frozen semantic state name
# ---------------------------------------------------------------------------
STATE_MAP = {
    (True, True, True): "READY",
    (False, True, True): "APP_LIMITED",
    (True, False, True): "FC_LIMITED",
    (True, True, False): "CC_LIMITED",
    (True, False, False): "MULTIPLE",
}


def bool_from_str(val: str) -> bool:
    """Convert ``"TRUE"`` / ``"FALSE"`` to ``bool``.

    The BPF events never contain ``UNKNOWN``; if they did we would raise.
    """
    if val == "TRUE":
        return True
    if val == "FALSE":
        return False
    raise ValueError(f"Unexpected predicate value for BPF event: {val}")


def main() -> None:
    # ---------------------------------------------------------------------
    # Paths
    # ---------------------------------------------------------------------
    base_dir = pathlib.Path("/home/rosa/experiments/tcp/TCP-CC-001/analysis")
    centered_dir = base_dir / "event_centered_output"
    tsv_path = centered_dir / "event_centered.tsv"

    out_dir = base_dir / "state_combination_output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------------
    # Load BPF events, validate predicates, and classify
    # ---------------------------------------------------------------------
    bpf_events: List[Dict[str, str]] = []
    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("source") != "BPF":
                continue
            # Extract predicates; they should all be present and binary
            try:
                d_bool = bool_from_str(row["pred_D"])
                f_bool = bool_from_str(row["pred_F"])
                c_bool = bool_from_str(row["pred_C"])
                r_bool = bool_from_str(row["pred_R"])
            except Exception as e:
                sys.stderr.write(f"Error parsing predicates for row: {e}\n")
                raise

            # Determine semantic state based on D/F/C triple
            state = STATE_MAP.get((d_bool, f_bool, c_bool), "UNSUPPORTED")
            row["state"] = state
            row["D_bool"] = d_bool
            row["F_bool"] = f_bool
            row["C_bool"] = c_bool
            row["R_bool"] = r_bool
            bpf_events.append(row)

    # ---------------------------------------------------------------------
    # Validation of total BPF event count
    # ---------------------------------------------------------------------
    total_bpf = len(bpf_events)
    sys.stderr.write(f"Validation: total BPF events = {total_bpf}\n")
    # Cross‑check with bpf_summary.txt
    summary_path = centered_dir / "bpf_summary.txt"
    expected = None
    with summary_path.open() as f:
        for line in f:
            if line.startswith("pred_D=TRUE"):
                # Format: pred_D=TRUE: 165456
                parts = line.strip().split(":")
                expected_true = int(parts[1].strip())
            if line.startswith("pred_D=FALSE"):
                parts = line.strip().split(":")
                expected_false = int(parts[1].strip())
    if expected_true is not None and expected_false is not None:
        expected_total = expected_true + expected_false
        if expected_total != total_bpf:
            sys.stderr.write(
                f"WARNING: BPF event count mismatch (summary {expected_total} vs actual {total_bpf})\n"
            )

    # ---------------------------------------------------------------------
    # Joint predicate counts (D,F,C)
    # ---------------------------------------------------------------------
    joint_counter: Counter[Tuple[bool, bool, bool]] = Counter()
    for ev in bpf_events:
        joint_counter[(ev["D_bool"], ev["F_bool"], ev["C_bool"])] += 1

    # Write joint_predicates.tsv – a compact view of each BPF event
    joint_path = out_dir / "joint_predicates.tsv"
    with joint_path.open("w", newline="") as f:
        fieldnames = ["raw_timestamp_ns", "pred_D", "pred_F", "pred_C", "pred_R", "state"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for ev in bpf_events:
            writer.writerow(
                {
                    "raw_timestamp_ns": ev.get("raw_timestamp_ns", ""),
                    "pred_D": ev["pred_D"],
                    "pred_F": ev["pred_F"],
                    "pred_C": ev["pred_C"],
                    "pred_R": ev["pred_R"],
                    "state": ev["state"],
                }
            )

    # ---------------------------------------------------------------------
    # Semantic state counts and R distribution per state
    # ---------------------------------------------------------------------
    state_counter: Counter[str] = Counter()
    r_true_counter: Counter[str] = Counter()
    r_false_counter: Counter[str] = Counter()
    for ev in bpf_events:
        st = ev["state"]
        state_counter[st] += 1
        if ev["R_bool"]:
            r_true_counter[st] += 1
        else:
            r_false_counter[st] += 1

    state_counts_path = out_dir / "semantic_state_counts.txt"
    with state_counts_path.open("w") as f:
        f.write("Semantic state counts (including unsupported combos)\n")
        for st, cnt in sorted(state_counter.items()):
            f.write(f"{st}: {cnt}\n")
        f.write("\nR distribution per state (TRUE / FALSE)\n")
        for st in sorted(state_counter.keys()):
            true_c = r_true_counter.get(st, 0)
            false_c = r_false_counter.get(st, 0)
            f.write(f"{st}: R_TRUE={true_c}, R_FALSE={false_c}\n")

    # ---------------------------------------------------------------------
    # Unsupported / ambiguous combos (those not in STATE_MAP)
    # ---------------------------------------------------------------------
    unsupported_counter: Counter[Tuple[bool, bool, bool]] = Counter()
    for combo, cnt in joint_counter.items():
        if combo not in STATE_MAP:
            unsupported_counter[combo] = cnt

    # ---------------------------------------------------------------------
    # Transition analysis – sort by raw_timestamp_ns (numeric)
    # ---------------------------------------------------------------------
    # Convert timestamp to int (fallback to 0 if missing)
    def ts_key(ev: Dict[str, str]) -> int:
        ts = ev.get("raw_timestamp_ns") or ev.get("bpf_timestamp_ns") or "0"
        try:
            return int(ts)
        except ValueError:
            return 0

    bpf_events.sort(key=ts_key)
    transitions: List[Tuple[int, str, int, str]] = []
    transition_counter: Counter[Tuple[str, str]] = Counter()
    for prev, nxt in zip(bpf_events, bpf_events[1:]):
        prev_ts = ts_key(prev)
        nxt_ts = ts_key(nxt)
        prev_state = prev["state"]
        nxt_state = nxt["state"]
        if prev_state != nxt_state:
            transitions.append((prev_ts, prev_state, nxt_ts, nxt_state))
            transition_counter[(prev_state, nxt_state)] += 1

    # Write observed_transitions.tsv
    trans_path = out_dir / "observed_transitions.tsv"
    with trans_path.open("w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["prev_timestamp_ns", "prev_state", "next_timestamp_ns", "next_state"])
        for pt, ps, nt, ns in transitions:
            writer.writerow([pt, ps, nt, ns])

    # ---------------------------------------------------------------------
    # Transition summary report
    # ---------------------------------------------------------------------
    summary_path = out_dir / "transition_summary.txt"
    with summary_path.open("w") as f:
        f.write("Most frequent state transitions (sorted by count)\n")
        for (src, dst), cnt in transition_counter.most_common(10):
            f.write(f"{src} -> {dst}: {cnt}\n")
        f.write("\nExamples of requested transitions (if present):\n")
        # Helper to locate first occurrence of a specific transition
        def find_example(src_state: str, dst_state: str) -> Tuple[Dict[str, str] | None, Dict[str, str] | None]:
            for prev, nxt in zip(bpf_events, bpf_events[1:]):
                if prev["state"] == src_state and nxt["state"] == dst_state:
                    return prev, nxt
            return None, None

        for src_state, dst_state in [("READY", "FC_LIMITED"), ("READY", "CC_LIMITED"), ("FC_LIMITED", "CC_LIMITED"), ("CC_LIMITED", "FC_LIMITED")]:
            pre, post = find_example(src_state, dst_state)
            if pre and post:
                f.write(f"{src_state} -> {dst_state}:\n")
                f.write(f"  prev_ts={pre.get('raw_timestamp_ns','?')} pred_D={pre['pred_D']} pred_F={pre['pred_F']} pred_C={pre['pred_C']} pred_R={pre['pred_R']}\n")
                f.write(f"  next_ts={post.get('raw_timestamp_ns','?')} pred_D={post['pred_D']} pred_F={post['pred_F']} pred_C={post['pred_C']} pred_R={post['pred_R']}\n")
            else:
                f.write(f"{src_state} -> {dst_state}: NOT OBSERVED\n")

        f.write("\nTransitions that skip intermediate states (e.g., READY -> MULTIPLE)\n")
        for (src, dst), cnt in transition_counter.items():
            # Define a simple adjacency rule: states differ by exactly one predicate value.
            # If more than one predicate changes, we call it a skip.
            # We'll compute Hamming distance on the D/F/C triple.
            def state_to_tuple(s: str) -> Tuple[int, int, int]:
                reverse = {v: k for k, v in STATE_MAP.items()}
                # If unsupported, we cannot map; treat as maximal distance.
                return reverse.get(s, (2, 2, 2))

            t1 = state_to_tuple(src)
            t2 = state_to_tuple(dst)
            # Hamming distance (number of bits that differ)
            dist = sum(1 for a, b in zip(t1, t2) if a != b)
            if dist > 1:
                f.write(f"{src} -> {dst}: {cnt} occurrences (distance {dist})\n")

    # ---------------------------------------------------------------------
    # Joint predicate table (summary) – write a readable text file
    # ---------------------------------------------------------------------
    joint_summary_path = out_dir / "joint_predicates_summary.txt"
    with joint_summary_path.open("w") as f:
        f.write("Joint D/F/C predicate counts (BPF events)\n")
        for combo, cnt in sorted(joint_counter.items()):
            d, f_, c = combo
            f.write(f"D={'TRUE' if d else 'FALSE'}, F={'TRUE' if f_ else 'FALSE'}, C={'TRUE' if c else 'FALSE'}: {cnt}\n")
        if unsupported_counter:
            f.write("\nUnsupported combos (not covered by frozen states):\n")
            for combo, cnt in unsupported_counter.items():
                d, f_, c = combo
                f.write(f"D={'TRUE' if d else 'FALSE'}, F={'TRUE' if f_ else 'FALSE'}, C={'TRUE' if c else 'FALSE'}: {cnt}\n")

    # ---------------------------------------------------------------------
    # Markdown report
    # ---------------------------------------------------------------------
    md_path = out_dir / "STATE_COMBINATION_ANALYSIS.md"
    with md_path.open("w") as f:
        f.write("# State‑Combination Analysis of BPF Observations\n\n")
        f.write(f"* Total BPF events processed: **{total_bpf}**\n\n")
        f.write("## Joint D/F/C predicate distribution\n\n```")
        for combo, cnt in sorted(joint_counter.items()):
            d, f_, c = combo
            f.write(f"D={'TRUE' if d else 'FALSE'}, F={'TRUE' if f_ else 'FALSE'}, C={'TRUE' if c else 'FALSE'}: {cnt}\n")
        f.write("```\n\n")
        f.write("## Semantic state counts (per frozen definition)\n\n```")
        for st, cnt in sorted(state_counter.items()):
            f.write(f"{st}: {cnt}\n")
        f.write("```\n\n")
        f.write("## R distribution within each state\n\n```")
        for st in sorted(state_counter.keys()):
            true_c = r_true_counter.get(st, 0)
            false_c = r_false_counter.get(st, 0)
            f.write(f"{st}: R_TRUE={true_c}, R_FALSE={false_c}\n")
        f.write("```\n\n")
        f.write("## Most frequent state transitions\n\n```")
        for (src, dst), cnt in transition_counter.most_common(10):
            f.write(f"{src} → {dst}: {cnt}\n")
        f.write("```\n\n")
        f.write("## Example transitions (timestamps and raw predicates)\n\n")
        for src_state, dst_state in [("READY", "FC_LIMITED"), ("READY", "CC_LIMITED"), ("FC_LIMITED", "CC_LIMITED"), ("CC_LIMITED", "FC_LIMITED")]:
            pre, post = None, None
            for p, n in zip(bpf_events, bpf_events[1:]):
                if p["state"] == src_state and n["state"] == dst_state:
                    pre, post = p, n
                    break
            if pre and post:
                f.write(f"### {src_state} → {dst_state}\n")
                f.write(f"* **Prev** ts={pre.get('raw_timestamp_ns','?')} D={pre['pred_D']} F={pre['pred_F']} C={pre['pred_C']} R={pre['pred_R']}\n")
                f.write(f"* **Next** ts={post.get('raw_timestamp_ns','?')} D={post['pred_D']} F={post['pred_F']} C={post['pred_C']} R={post['pred_R']}\n\n")
            else:
                f.write(f"### {src_state} → {dst_state}: NOT OBSERVED\n\n")
        f.write("## Unsupported/ambiguous combinations\n\n")
        if unsupported_counter:
            for combo, cnt in unsupported_counter.items():
                d, f_, c = combo
                f.write(f"- D={'TRUE' if d else 'FALSE'}, F={'TRUE' if f_ else 'FALSE'}, C={'TRUE' if c else 'FALSE'}: {cnt}\n")
        else:
            f.write("_None – every BPF event maps to a defined state._\n")

    # ---------------------------------------------------------------------
    # Final console summary (stderr)
    # ---------------------------------------------------------------------
    sys.stderr.write("State‑combination analysis completed. Outputs written to " + str(out_dir) + "\n")


if __name__ == "__main__":
    main()