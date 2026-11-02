#!/usr/bin/env python3
"""event_centered_analysis.py – Offline, event‑by‑event evaluation of TCP predicates.

This script is a lightweight companion to the original ``semantic_correlation.py``.
It **does not** merge the three observation streams on exact timestamps.  Instead it
preserves each observation as an independent event, records its provenance (source,
run identifier, original timestamp and clock domain) and evaluates the four frozen
predicates **only when the necessary fields are present**.

The model follows the definitions used in the frozen state machine:

* **D – HasTransportPendingData** – evaluated from ``tcpi_notsent_bytes`` (TCP_INFO)
  or from ``write_seq``/``snd_nxt`` (BPF).  The correct direction is
  ``write_seq - snd_nxt``; ambiguous wrap‑around (difference > 2**31) yields
  ``UNKNOWN``.
* **F – FlowControlAllowsNewData** – based on ``snd_wnd`` and the in‑flight byte
  count ``snd_nxt - snd_una``.  Unsigned subtraction is performed modulo 2¹⁶, and the
  result is compared with the advertised window.  If the in‑flight value exceeds the
  window the predicate is ``FALSE``; if the calculation is ambiguous (wrap‑around) it
  is ``UNKNOWN``.
* **C – CongestionControlAllowsNewData** – uses the kernel packet accounting helper
  ``tcp_packets_in_flight``: ``packets_out - (sacked_out + lost_out) + retrans_out``
  compared against ``snd_cwnd`` (packet units).  The check yields ``TRUE`` when head‑
  room exists, ``FALSE`` otherwise.
* **R – InRecovery** – true only for ``ca_state`` values 3 (CA_RECOVERY) or 4
  (CA_LOSS).  ``TCP_CA_CWR`` (value 2) is recorded separately but does not set the
  predicate.

The script reads the three artefacts from a *verified* smoke run (APP CSV, TCP_INFO
CSV, BPF log) together with the two clock‑offset files that map the BPF monotonic
timestamps to the ``CLOCK_MONOTONIC_RAW`` domain used by the CSVs.

Outputs are written to a **new** directory (by default
``analysis/event_centered_output``) and include:

* ``event_centered.tsv`` – a tab‑separated table of all events with original fields
  and derived predicates.
* ``overall_summary.txt`` – counts of TRUE/FALSE/UNKNOWN for each predicate over all
  events.
* ``per_source_summary.txt`` – the same counts broken down by source (APP, BPF,
  TCP_INFO).
* ``bpf_summary.txt`` and ``tcpinfo_summary.txt`` – convenient one‑line summaries.
* ``explanation.txt`` – description of which predicates are directly observed,
  derived, proxied, or UNKNOWN.
* ``comparison.txt`` – a diff against the historic exact‑timestamp summary (if it
  exists).

No raw artefacts are modified and the original ``semantic_correlation.py`` remains
unchanged.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Helper constants and functions (copied from semantic_correlation.py)
# ---------------------------------------------------------------------------
SEQ_MOD = 2 ** 32

def seq_diff(a: int, b: int) -> int:
    """Return (a - b) modulo 2^32 as an unsigned integer.

    ``a`` is expected to be the later sequence number, ``b`` the earlier one.
    The result is in the range ``0 .. 2**32-1``.
    """
    return (a - b) % SEQ_MOD

def load_offset_file(path: pathlib.Path) -> Tuple[int, int, int, int, int, int]:
    """Parse a ``clock_offset_*.txt`` file.

    The file contains a single line with six space‑separated integers:
    ``raw_before mono raw_after raw_mid offset_uncert`` (as in the original
    script).  The function returns these six values as a tuple of ``int``.
    """
    with path.open() as f:
        parts = f.read().strip().split()
    if len(parts) != 6:
        raise ValueError(f"Unexpected format in offset file {path}")
    return tuple(int(p) for p in parts)  # type: ignore[return-value]

def build_offset_interpolator(
    pre: Tuple[int, int, int, int, int, int],
    post: Tuple[int, int, int, int, int, int],
):
    """Return a function ``offset(ts)`` that linearly interpolates the clock drift.

    ``pre`` and ``post`` are the tuples obtained from ``load_offset_file`` for the
    measurements taken before and after the experiment.
    """
    _, mono_pre, _, _, _, _ = pre
    _, mono_post, _, _, _, _ = post
    denom = mono_post - mono_pre if mono_post != mono_pre else 1
    def offset(ts: int) -> int:
        offset_pre = pre[4]
        offset_post = post[4]
        return int(offset_pre + (offset_post - offset_pre) * (ts - mono_pre) / denom)
    return offset

# ---------------------------------------------------------------------------
# CSV / log parsing – identical to the original implementation except that we
# retain the original timestamp field name and later rename it to avoid clashes.
# ---------------------------------------------------------------------------
def parse_app_log(path: pathlib.Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open() as f:
        reader = csv.DictReader(filter(lambda l: not l.startswith('#'), f))
        for r in reader:
            rows.append(r)
    return rows

def parse_tcpinfo_log(path: pathlib.Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open() as f:
        reader = csv.DictReader(filter(lambda l: not l.startswith('#'), f))
        for r in reader:
            rows.append(r)
    return rows

def parse_bpf_log(path: pathlib.Path, offset_func) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open() as f:
        lines = f.readlines()
    if len(lines) < 3:
        return rows
    header = lines[1].strip().split()
    field_names = header
    for line in lines[2:]:
        if not line.strip():
            continue
        parts = line.strip().split()
        if len(parts) != len(field_names):
            continue
        entry = dict(zip(field_names, parts))
        try:
            mono_ts = int(entry["timestamp_ns"])
        except Exception:
            continue
        raw_ts = mono_ts - offset_func(mono_ts)
        entry["raw_timestamp_ns"] = str(raw_ts)
        rows.append(entry)
    return rows

# ---------------------------------------------------------------------------
# Predicate evaluation – event‑centric version.
# ---------------------------------------------------------------------------
def evaluate_event_predicates(row: Dict[str, str]) -> Dict[str, str]:
    """Return a dict with keys ``pred_D``, ``pred_F``, ``pred_C`` and ``pred_R``.

    The function inspects the fields present in ``row`` and applies the frozen
    definitions.  When a predicate cannot be evaluated because the required
    measurements are missing, the result is ``UNKNOWN``.
    """
    result = {"pred_D": "UNKNOWN", "pred_F": "UNKNOWN", "pred_C": "UNKNOWN", "pred_R": "UNKNOWN"}

    # ----- D – pending transport data -------------------------------------
    if "tcpi_notsent_bytes" in row:
        try:
            notsent = int(row["tcpi_notsent_bytes"])
            result["pred_D"] = "TRUE" if notsent > 0 else "FALSE"
        except ValueError:
            result["pred_D"] = "UNKNOWN"
    elif "write_seq" in row and "snd_nxt" in row:
        try:
            write_seq = int(row["write_seq"])
            snd_nxt = int(row["snd_nxt"])
            diff = seq_diff(write_seq, snd_nxt)
            if diff == 0:
                result["pred_D"] = "FALSE"
            elif diff > 0x7FFFFFFF:
                result["pred_D"] = "UNKNOWN"
            else:
                result["pred_D"] = "TRUE"
        except ValueError:
            result["pred_D"] = "UNKNOWN"

    # ----- F – flow‑control credit ---------------------------------------
    if all(k in row for k in ("snd_wnd", "snd_nxt", "snd_una")):
        try:
            snd_wnd = int(row["snd_wnd"])
            snd_nxt = int(row["snd_nxt"])
            snd_una = int(row["snd_una"])
            in_flight = seq_diff(snd_nxt, snd_una)
            if in_flight > 0x7FFFFFFF:
                result["pred_F"] = "UNKNOWN"
            elif in_flight > snd_wnd:
                result["pred_F"] = "FALSE"
            else:
                credit = snd_wnd - in_flight
                result["pred_F"] = "TRUE" if credit > 0 else "FALSE"
        except ValueError:
            result["pred_F"] = "UNKNOWN"

    # ----- C – congestion‑window headroom ---------------------------------
    if all(k in row for k in ("snd_cwnd", "packets_out", "sacked_out", "lost_out", "retrans_out")):
        try:
            snd_cwnd = int(row["snd_cwnd"])
            packets_out = int(row["packets_out"])
            sacked_out = int(row["sacked_out"])
            lost_out = int(row["lost_out"])
            retrans_out = int(row["retrans_out"])
            in_flight_pkt = packets_out - (sacked_out + lost_out) + retrans_out
            headroom = snd_cwnd - in_flight_pkt
            result["pred_C"] = "TRUE" if headroom > 0 else "FALSE"
        except ValueError:
            result["pred_C"] = "UNKNOWN"

    # ----- R – in recovery (loss‑recovery only) --------------------------
    if "ca_state" in row:
        try:
            state = int(row["ca_state"])
            result["pred_R"] = "TRUE" if state in (3, 4) else "FALSE"
        except ValueError:
            result["pred_R"] = "UNKNOWN"

    return result

# ---------------------------------------------------------------------------
# Summary utilities
# ---------------------------------------------------------------------------
def tally_predictions(rows: List[Dict[str, str]]) -> Tuple[Dict[str, Counter], Counter]:
    """Return per‑source counters and an overall counter for each predicate.

    ``per_source`` maps source name → Counter of ``pred_X=TRUE/FALSE/UNKNOWN``.
    ``overall`` aggregates across all sources.
    """
    per_source: Dict[str, Counter] = defaultdict(Counter)
    overall: Counter = Counter()
    for r in rows:
        src = r.get("source", "UNKNOWN")
        for pred in ("pred_D", "pred_F", "pred_C", "pred_R"):
            val = r.get(pred, "UNKNOWN")
            key = f"{pred}={val}"
            per_source[src][key] += 1
            overall[key] += 1
    return per_source, overall

def write_summary(path: pathlib.Path, counter: Counter, title: str) -> None:
    with path.open("w") as f:
        f.write(f"{title}\n")
        for key, cnt in sorted(counter.items()):
            f.write(f"{key}: {cnt}\n")

# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Event‑centered analysis of TCP_CC predicates.")
    parser.add_argument(
        "--run-dir",
        type=pathlib.Path,
        required=False,
        default=pathlib.Path("/home/rosa/experiments/tcp/TCP-CC-001/monitor/smoke-1791488316-YJK6"),
        help="Directory containing sender_app_log.csv, sender_tcpinfo_log.csv, bpf_events.log and offset files.",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=pathlib.Path("/home/rosa/experiments/tcp/TCP-CC-001/analysis/event_centered_output"),
        help="Directory where new analysis artefacts will be written.",
    )
    args = parser.parse_args()

    run_dir: pathlib.Path = args.run_dir.resolve()
    out_dir: pathlib.Path = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_dir.name

    # ---------------------------------------------------------------------
    # Load artefacts
    # ---------------------------------------------------------------------
    app_log = parse_app_log(run_dir / "sender_app_log.csv")
    tcpinfo_log = parse_tcpinfo_log(run_dir / "sender_tcpinfo_log.csv")
    pre_offset = load_offset_file(run_dir / "clock_offset_pre.txt")
    post_offset = load_offset_file(run_dir / "clock_offset_post.txt")
    offset_fn = build_offset_interpolator(pre_offset, post_offset)
    bpf_log = parse_bpf_log(run_dir / "bpf_events.log", offset_fn)

    # ---------------------------------------------------------------------
    # Normalise / tag rows – keep original timestamps and add provenance.
    # ---------------------------------------------------------------------
    for r in app_log:
        r["app_timestamp_ns"] = r.pop("timestamp_ns")
        r["source"] = "APP"
        r["run_id"] = run_id

    for r in tcpinfo_log:
        r["tcp_timestamp_ns"] = r.pop("timestamp_ns")
        r["source"] = "TCP_INFO"
        r["run_id"] = run_id

    for r in bpf_log:
        r["bpf_timestamp_ns"] = r.pop("timestamp_ns")
        r["source"] = "BPF"
        r["run_id"] = run_id
        # raw_timestamp_ns already present from conversion

    all_events: List[Dict[str, str]] = app_log + tcpinfo_log + bpf_log

    # ---------------------------------------------------------------------
    # Evaluate predicates per event
    # ---------------------------------------------------------------------
    for ev in all_events:
        ev.update(evaluate_event_predicates(ev))

    # ---------------------------------------------------------------------
    # Write the combined event table (TSV)
    # ---------------------------------------------------------------------
    tsv_path = out_dir / "event_centered.tsv"
    all_keys = sorted({k for row in all_events for k in row.keys()})
    with tsv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, delimiter="\t")
        writer.writeheader()
        for row in all_events:
            writer.writerow(row)

    # ---------------------------------------------------------------------
    # Summaries
    # ---------------------------------------------------------------------
    per_source, overall = tally_predictions(all_events)
    write_summary(out_dir / "overall_summary.txt", overall, "Overall predicate counts")
    per_src_path = out_dir / "per_source_summary.txt"
    with per_src_path.open("w") as f:
        f.write("Per‑source predicate counts\n")
        for src, cnt in sorted(per_source.items()):
            f.write(f"--- {src} ---\n")
            for key, val in sorted(cnt.items()):
                f.write(f"{key}: {val}\n")
            f.write("\n")
    write_summary(out_dir / "bpf_summary.txt", per_source.get("BPF", Counter()), "BPF predicate counts")
    write_summary(out_dir / "tcpinfo_summary.txt", per_source.get("TCP_INFO", Counter()), "TCP_INFO predicate counts")

    # ---------------------------------------------------------------------
    # Explanation of provenance
    # ---------------------------------------------------------------------
    expl_path = out_dir / "explanation.txt"
    with expl_path.open("w") as f:
        f.write("Predicate provenance for event‑centered analysis:\n")
        f.write("* D – direct from tcpi_notsent_bytes (TCP_INFO) or from write_seq‑snd_nxt (BPF).\n")
        f.write("* F – derived from snd_wnd, snd_nxt, snd_una (BPF) using signed wrap‑aware logic.\n")
        f.write("* C – derived from snd_cwnd and packet counters (BPF) – a proxy for cwnd headroom.\n")
        f.write("* R – true only for ca_state values 3 (CA_RECOVERY) or 4 (CA_LOSS) (BPF).\n")
        f.write("* APP events contain no transport state; all predicates are UNKNOWN for them.\n")

    # ---------------------------------------------------------------------
    # Comparison with historic exact‑timestamp summary (if available)
    # ---------------------------------------------------------------------
    historic_path = pathlib.Path("/home/rosa/experiments/tcp/TCP-CC-001/analysis/output/semantic_summary.txt")
    if historic_path.is_file():
        hist_counts: Dict[str, Tuple[int, int, int]] = {}
        with historic_path.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("Merged events"):
                    continue
                if ":" in line:
                    pred, rest = line.split(":", 1)
                    parts = rest.split(",")
                    true_val = int(parts[0].split("=")[1])
                    false_val = int(parts[1].split("=")[1])
                    unk_val = int(parts[2].split("=")[1])
                    hist_counts[pred.strip()] = (true_val, false_val, unk_val)
        curr_counts: Dict[str, Tuple[int, int, int]] = {}
        for pred in ("pred_D", "pred_F", "pred_C", "pred_R"):
            true_c = overall.get(f"{pred}=TRUE", 0)
            false_c = overall.get(f"{pred}=FALSE", 0)
            unk_c = overall.get(f"{pred}=UNKNOWN", 0)
            curr_counts[pred[5:]] = (true_c, false_c, unk_c)
        comp_path = out_dir / "comparison.txt"
        with comp_path.open("w") as f:
            f.write("Comparison with historic exact‑timestamp summary:\n")
            for pred in sorted(hist_counts.keys()):
                h_true, h_false, h_unk = hist_counts[pred]
                c_true, c_false, c_unk = curr_counts.get(pred, (0, 0, 0))
                f.write(
                    f"{pred}: HIST TRUE={h_true}, CURR TRUE={c_true} (Δ={c_true - h_true}); "
                    f"HIST FALSE={h_false}, CURR FALSE={c_false} (Δ={c_false - h_false}); "
                    f"HIST UNKNOWN={h_unk}, CURR UNKNOWN={c_unk} (Δ={c_unk - h_unk})\n"
                )

    # ---------------------------------------------------------------------
    # Simple validation printout
    # ---------------------------------------------------------------------
    total_events = len(all_events)
    app_events = len(app_log)
    tcpinfo_events = len(tcpinfo_log)
    bpf_events = len(bpf_log)
    sys.stderr.write(
        f"Validation: total events = {total_events} (APP={app_events}, TCP_INFO={tcpinfo_events}, BPF={bpf_events})\n"
    )
    if bpf_events >= 3:
        sys.stderr.write("Sample BPF predicate evaluations (first three rows):\n")
        for i in range(3):
            row = bpf_log[i]
            preds = {k: row.get(k) for k in ("pred_D", "pred_F", "pred_C", "pred_R")}
            sys.stderr.write(f"  Row {i+1}: {preds}\n")
    sys.stderr.write("Event‑centered analysis completed. Outputs written to " + str(out_dir) + "\n")

if __name__ == "__main__":
    main()