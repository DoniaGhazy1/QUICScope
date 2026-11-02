#!/usr/bin/env python3
"""Diagnostic analysis of TCP‑FC‑001 run‑001 reconstruction.

Purpose
=======
The original ``analyze_passive_fc.py`` computed a *passive usable credit*
value that became negative (≈ ‑128 459 104 bytes).  This script reproduces the
packet‑level processing in order to:

1. Identify the first packet/event where the negative credit occurs and show
   the full TCP state around that moment.
2. Verify the RFC‑9293 window‑update semantics (advertised right edge =
   ``SEG.ACK + SEG.WND``) and compare it with the stateful ``snd_una + snd_wnd``
   model used by the original script.
3. Inspect all zero‑window advertisements and the first positive‑window
   advertisement after the zero‑window period.
4. Analyse the sender payload‑size distribution to detect possible TSO/GSO
   off‑load effects.
5. Summarise findings in ``fc-reconstruction-debug.md``.

The script operates *offline* on the existing artifacts only – it does not
modify any raw files.
"""

import os
import re
import subprocess
import sys
from collections import defaultdict
from statistics import median


# ---------------------------------------------------------------------------
# Configuration – connection of interest (hard‑coded for this experiment)
# ---------------------------------------------------------------------------
CLIENT_IP = "192.168.88.20"
CLIENT_PORT = "55208"
SERVER_IP = "192.168.88.21"
SERVER_PORT = "5203"


def run_tcpdump(capture_path):
    """Yield tcpdump lines with timestamps (``-tt``) for *capture_path*.

    Returns an iterator of raw packet description lines.
    """
    try:
        proc = subprocess.Popen(
            ["tcpdump", "-nn", "-tt", "-r", capture_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        sys.stderr.write("ERROR: tcpdump not found – cannot analyse capture.\n")
        sys.exit(1)

    for line in proc.stdout:
        line = line.rstrip("\n")
        if line.startswith("reading from file"):
            continue
        if not line:
            continue
        yield line
    proc.wait()
    if proc.returncode not in (0, None):
        sys.stderr.write(f"tcpdump error: {proc.stderr.read()}\n")
        sys.exit(1)


def parse_syn_options(line: str):
    """Extract MSS and wscale from a SYN or SYN‑ACK line.

    Returns (mss, wscale) where each may be ``None``.
    """
    mss_match = re.search(r"mss (\d+)", line)
    wscale_match = re.search(r"wscale (\d+)", line)
    mss = int(mss_match.group(1)) if mss_match else None
    wscale = int(wscale_match.group(1)) if wscale_match else None
    return mss, wscale


def main():
    run_dir = os.path.abspath(os.path.dirname(__file__))
    capture_path = os.path.join(run_dir, "tcp_capture.pcap")
    out_md = os.path.join(run_dir, "fc-reconstruction-debug.md")

    # -------------------------------------------------------------------
    # State variables
    # -------------------------------------------------------------------
    scale_factor = None  # 2**WSCALE from SYN‑ACK
    mss = None
    # Lists for analysis
    zero_win_records = []   # list of dicts for zero‑window ACKs
    ack_records = []        # all ACKs from server (including zero‑window)
    data_lengths = []       # payload lengths of client‑to‑server data packets
    # Reconstructed TCP state (RFC 9293 variables)
    snd_nxt = 0   # highest sequence number *sent* (observed on wire)
    snd_una = 0   # last cumulative ACK received from receiver
    snd_wnd = 0   # latest advertised window (scaled)
    # Credit tracking
    credit_records = []
    first_negative = None
    # Direct right‑edge tracking (per‑ACK calculation)
    direct_edge_records = []

    # -------------------------------------------------------------------
    # Process packets
    # -------------------------------------------------------------------
    for line in run_tcpdump(capture_path):
        # Example line layout (already observed previously):
        # 1791402957.961831 IP 192.168.88.20.55208 > 192.168.88.21.5203: Flags [S], seq 2927657205, win 64240, options [mss 1460,sackOK,TS val 3264414472 ecr 0,nop,wscale 7], length 0
        parts = line.split()
        if len(parts) < 6:
            continue
        ts = float(parts[0])
        src = parts[2]
        dst = parts[4]
        if dst.endswith(":"):
            dst = dst[:-1]
        src_ip, src_port = src.rsplit('.', 1)
        dst_ip, dst_port = dst.rsplit('.', 1)

        # Only keep packets that belong to our flow.
        if not (
            (src_ip == CLIENT_IP and src_port == CLIENT_PORT and dst_ip == SERVER_IP and dst_port == SERVER_PORT)
            or (src_ip == SERVER_IP and src_port == SERVER_PORT and dst_ip == CLIENT_IP and dst_port == CLIENT_PORT)
        ):
            continue

        # Extract flags
        flags_match = re.search(r"Flags \[([^]]+)\]", line)
        flags = flags_match.group(1) if flags_match else ""
        # Raw window (present on every packet after "win ")
        raw_win = None
        win_match = re.search(r"win (\d+)", line)
        if win_match:
            raw_win = int(win_match.group(1))

        # ----------------------------------------------------------------
        # Handshake processing – capture scale factor and MSS once.
        # ----------------------------------------------------------------
        if src_ip == CLIENT_IP and "S" in flags and not ("." in flags):  # SYN
            mss_syn, wscale_syn = parse_syn_options(line)
            if mss_syn:
                mss = mss_syn
            # SYN window is not used for scaling, keep for completeness.
            continue
        if src_ip == SERVER_IP and "S" in flags and "." in flags:  # SYN‑ACK
            mss_synack, wscale_synack = parse_syn_options(line)
            if mss_synack:
                mss = mss_synack
            if wscale_synack is not None:
                scale_factor = 1 << wscale_synack
            continue

        # ---------------------------------------------------------------
        # Data packets (client -> server, flag P)
        # ---------------------------------------------------------------
        if src_ip == CLIENT_IP and "P" in flags:
            # Sequence range
            seq_match = re.search(r"seq (\d+):(\d+)", line)
            if seq_match:
                seq_start = int(seq_match.group(1))
                seq_end = int(seq_match.group(2))
                # Update snd_nxt (high water mark)
                if seq_end > snd_nxt:
                    snd_nxt = seq_end
                # Record payload length (if present)
                length_match = re.search(r"length (\d+)", line)
                if length_match:
                    data_lengths.append(int(length_match.group(1)))
            continue

        # ---------------------------------------------------------------
        # ACK packets from server -> client (may also carry window)
        # ---------------------------------------------------------------
        if src_ip == SERVER_IP:
            ack_match = re.search(r"ack (\d+)", line)
            if not ack_match:
                continue
            ack_val = int(ack_match.group(1))
            # Update snd_una (cumulative ACK)
            prev_una = snd_una
            snd_una = max(snd_una, ack_val)
            # Window scaling – raw_win may be None (unlikely for ACK), default 0
            scaled_win = (raw_win << (int(scale_factor).bit_length() - 1)) if (raw_win is not None and scale_factor) else 0
            # However, the scaling should be raw_win << wscale (where wscale is log2(scale_factor)).
            # Compute wscale explicitly for correctness.
            wscale = (scale_factor.bit_length() - 1) if scale_factor else 0
            scaled_win = raw_win << wscale if raw_win is not None else 0
            # Record ACK entry
            ack_entry = {
                "ts": ts,
                "raw_win": raw_win,
                "scaled_win": scaled_win,
                "ack": ack_val,
                "prev_una": prev_una,
                "snd_wnd_before": snd_wnd,
                "snd_wnd_after": scaled_win,
            }
            ack_records.append(ack_entry)
            # Detect zero‑window
            if raw_win == 0:
                zero_win_records.append(ack_entry)
            # Update snd_wnd (the advertised window from this ACK)
            snd_wnd = scaled_win

            # Compute credit using the stateful model (snd_una + snd_wnd - snd_nxt)
            credit = snd_una + snd_wnd - snd_nxt
            credit_records.append({"ts": ts, "credit": credit, "snd_nxt": snd_nxt, "snd_una": snd_una, "snd_wnd": snd_wnd})
            if credit < 0 and first_negative is None:
                # Record the first negative credit event with surrounding state
                first_negative = {
                    "ts": ts,
                    "direction": "server->client",
                    "seq": ack_val,  # ACK uses the ack field as sequence number for the receiver side
                    "ack": ack_val,
                    "raw_win": raw_win,
                    "scaled_win": scaled_win,
                    "snd_una_before": prev_una,
                    "snd_una_after": snd_una,
                    "snd_wnd_before": ack_entry["snd_wnd_before"],
                    "snd_wnd_after": snd_wnd,
                    "snd_nxt": snd_nxt,
                    "credit": credit,
                }
            # Direct right‑edge (SEG.ACK + scaled_window) for comparison
            direct_edge = ack_val + scaled_win
            direct_edge_records.append({"ts": ts, "ack": ack_val, "scaled_win": scaled_win, "right_edge": direct_edge, "snd_nxt": snd_nxt})
            continue

    # -------------------------------------------------------------------
    # Determine statistics for payload sizes (TSO/GSO detection)
    # -------------------------------------------------------------------
    if data_lengths:
        min_len = min(data_lengths)
        max_len = max(data_lengths)
        med_len = median(data_lengths)
        count_gt_mss = sum(1 for l in data_lengths if l > (mss or 1460))
        # Representative large packet – first exceeding MSS
        large_pkt_len = next((l for l in data_lengths if l > (mss or 1460)), None)
    else:
        min_len = max_len = med_len = count_gt_mss = large_pkt_len = 0

    # -------------------------------------------------------------------
    # Helper to format timestamps with six decimal places (microseconds)
    # -------------------------------------------------------------------
    fmt_ts = lambda t: f"{t:.6f}" if t is not None else "-"

    # -------------------------------------------------------------------
    # Build markdown report
    # -------------------------------------------------------------------
    with open(out_md, "w", encoding="utf-8") as md:
        md.write("# TCP Flow‑Control Reconstruction Debug – run‑001\n\n")
        md.write("## Handshake information\n\n")
        md.write(f"* Negotiated window‑scale = {scale_factor.bit_length() - 1 if scale_factor else 'unknown'}\n")
        md.write(f"* Negotiated MSS = {mss if mss else 'unknown'}\n\n")

        # ---- First negative credit ------------------------------------------------
        md.write("## First event where passive usable credit becomes negative\n\n")
        if first_negative:
            fn = first_negative
            md.write(f"* Timestamp (pcap)            : {fmt_ts(fn['ts'])}\n")
            md.write(f"* Direction                  : {fn['direction']}\n")
            md.write(f"* SEG.ACK (receiver ACK)     : {fn['ack']}\n")
            md.write(f"* Raw Window                 : {fn['raw_win']}\n")
            md.write(f"* Scaled Window              : {fn['scaled_win']}\n")
            md.write(f"* snd_una before             : {fn['snd_una_before']}\n")
            md.write(f"* snd_una after              : {fn['snd_una_after']}\n")
            md.write(f"* snd_wnd before             : {fn['snd_wnd_before']}\n")
            md.write(f"* snd_wnd after              : {fn['snd_wnd_after']}\n")
            md.write(f"* snd_nxt (high‑water)       : {fn['snd_nxt']}\n")
            md.write(f"* Advertised right edge (snd_una+snd_wnd) : {fn['snd_una_after'] + fn['snd_wnd_after']}\n")
            md.write(f"* Resulting usable credit    : {fn['credit']}\n")
        else:
            md.write("No negative credit discovered – this contradicts the earlier quantitative file.\n")
        md.write("\n")

        # ---- Zero‑window advertisements ------------------------------------------
        md.write("## Zero‑window advertisement snapshots\n\n")
        def describe_zwin(rec):
            return (
                f"* ts={fmt_ts(rec['ts'])}, ack={rec['ack']}, raw_win={rec['raw_win']}, "
                f"scaled_win={rec['scaled_win']}, snd_nxt={snd_nxt}, "
                f"snd_una_before={rec['prev_una']}, snd_una_after={rec['ack']}"
            )
        if zero_win_records:
            md.write(f"* First zero‑window ACK ({len(zero_win_records)} total):\n")
            md.write(describe_zwin(zero_win_records[0]) + "\n")
            # Middle record – pick the one at index len//2
            mid_idx = len(zero_win_records) // 2
            md.write("* Middle zero‑window ACK:\n")
            md.write(describe_zwin(zero_win_records[mid_idx]) + "\n")
            md.write("* Last zero‑window ACK:\n")
            md.write(describe_zwin(zero_win_records[-1]) + "\n")
        else:
            md.write("No zero‑window advertisements were observed.\n")
        md.write("\n")

        # ---- First positive window after zero -----------------------------------
        md.write("## First positive‑window update after zero‑window period\n\n")
        first_pos = None
        if zero_win_records:
            last_zero_ts = zero_win_records[-1]["ts"]
            for rec in ack_records:
                if rec["ts"] > last_zero_ts and rec["raw_win"] > 0:
                    first_pos = rec
                    break
        if first_pos:
            md.write(f"* Timestamp                 : {fmt_ts(first_pos['ts'])}\n")
            md.write(f"* ACK value                 : {first_pos['ack']}\n")
            md.write(f"* Raw Window                : {first_pos['raw_win']}\n")
            md.write(f"* Scaled Window             : {first_pos['scaled_win']}\n")
        else:
            md.write("No positive window found after zero‑window period.\n")
        md.write("\n")

        # ---- Direct right‑edge vs sender high‑water ------------------------------
        md.write("## Direct advertised right‑edge (ACK+scaled_window) vs snd_nxt\n\n")
        negative_direct = []
        for rec in direct_edge_records:
            if rec["right_edge"] < rec["snd_nxt"]:
                negative_direct.append(rec)
        if negative_direct:
            md.write(f"* Instances where ACK+window < snd_nxt: {len(negative_direct)}\n")
            md.write("  (first occurrence)\n")
            r = negative_direct[0]
            md.write(f"  ts={fmt_ts(r['ts'])}, ack={r['ack']}, scaled_win={r['scaled_win']}, right_edge={r['right_edge']}, snd_nxt={r['snd_nxt']}\n")
        else:
            md.write("* No case where ACK+scaled_window fell below snd_nxt – direct right‑edge stays >= snd_nxt.\n")
        md.write("\n")

        # ---- Payload size distribution ------------------------------------------
        md.write("## Sender payload‑size distribution (possible TSO/GSO)\n\n")
        md.write(f"* Minimum payload length   : {min_len}\n")
        md.write(f"* Median payload length    : {med_len}\n")
        md.write(f"* Maximum payload length   : {max_len}\n")
        md.write(f"* Packets with length > MSS ({mss if mss else 1460}) : {count_gt_mss}\n")
        md.write(f"* Example large packet length : {large_pkt_len}\n\n")

        # ---- Window‑scale verification ------------------------------------------
        md.write("## Window‑scale verification (raw → scaled)\n\n")
        # Show a few representative samples: early, mid, zero, reopening
        sample_indices = [0, len(ack_records)//4, len(ack_records)//2, len(ack_records)-1]
        for idx in sample_indices:
            if 0 <= idx < len(ack_records):
                rec = ack_records[idx]
                md.write(f"* ts={fmt_ts(rec['ts'])}, raw_win={rec['raw_win']}, scaled_win={rec['scaled_win']}\n")
        md.write("\n")

        # ---- Summary of credit computation --------------------------------------
        md.write("## Credit computation summary\n\n")
        min_credit = min((c["credit"] for c in credit_records), default=0)
        md.write(f"* Minimum stateful credit (snd_una+snd_wnd‑snd_nxt) : {min_credit}\n")
        md.write(f"* Zero‑credit observed (stateful) : {'yes' if any(c['credit'] == 0 for c in credit_records) else 'no'}\n")
        md.write("\n")

        md.write("---\n")
        md.write("*This file is generated automatically for debugging purposes.*\n")

    print(f"Debug analysis written to {out_md}")


if __name__ == "__main__":
    main()
