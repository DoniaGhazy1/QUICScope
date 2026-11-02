#!/usr/bin/env python3
"""Passive analysis of TCP‑APP‑001 run‑004.

Purpose
=======
Parse the textual output of the pcap captured for run‑004 and compute, for each
application‑controlled pause, whether the *sequence‑space outstanding estimate*
reaches zero before the next ``pre_send`` event recorded in
``controlled_workload_timeline.log``.

The outstanding estimate is defined (as in TCP‑BASE‑001) as:

    outstanding = (sender high‑water‑mark of payload sequence numbers, including
                  one byte for the SYN and one for the FIN) – (largest cumulative
                  ACK observed from the receiver).

It is a **WIRE_DERIVED** quantity – an observer‑level estimate, not the kernel
``bytes_in_flight`` counter.

The script prints a tab‑separated table with one line per pause (0‑18) and a
final line for the last pause (19) which has no subsequent ``pre_send``.
"""

import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration – paths relative to this script's location
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
TIMELINE_PATH = BASE_DIR / "controlled_workload_timeline.log"
PCAP_PATH = BASE_DIR / "tcp_capture.pcap"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def ns_from_ts(ts_str: str) -> int:
    """Convert a tcpdump timestamp (seconds.micros) to integer nanoseconds."""
    # tcpdump prints seconds with decimal fraction up to microseconds
    sec, *frac = ts_str.split('.')
    sec = int(sec)
    # pad fraction to 9 digits to get nanoseconds
    frac_part = (frac[0] if frac else "0").ljust(9, "0")[:9]
    return sec * 1_000_000_000 + int(frac_part)

def parse_timeline(path: Path):
    """Parse ``controlled_workload_timeline.log``.

    The file is a simple CSV with columns ``event,timestamp_ns,rep,...``.
    ``rep`` is empty for ``conn_established`` which we ignore.

    Returns a dict mapping ``rep`` (int) → ``{event: timestamp_ns}``.
    """
    timeline: dict[int, dict[str, int]] = {}
    with path.open() as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) < 3:
                continue
            event = parts[0]
            ts_str = parts[1]
            rep_str = parts[2]
            # ``rep`` may be empty for lines we don't care about.
            if not rep_str:
                continue
            try:
                rep = int(rep_str)
                ts = int(ts_str)
            except ValueError:
                # Skip malformed lines.
                continue
            timeline.setdefault(rep, {})[event] = ts
    return timeline

def run_tcpdump(pcap_path: Path):
    """Yield each line of ``tcpdump -nn -tt -r <pcap>`` as a string.

    The command prints timestamps as seconds.microseconds (epoch).  We keep the
    raw line for further regex parsing.
    """
    cmd = ["tcpdump", "-nn", "-tt", "-r", str(pcap_path)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Iterate line‑by‑line; the pcap is small (≈ 17 kB) so this is fine.
    for line in proc.stdout:
        yield line.rstrip("\n")
    proc.wait()
    if proc.returncode != 0:
        sys.stderr.write(f"tcpdump failed for {pcap_path}\n")
        sys.exit(1)

def analyze():
    timeline = parse_timeline(TIMELINE_PATH)
    # Build ordered list of reps (0‑19 expected)
    reps = sorted(timeline.keys())
    if not reps:
        sys.stderr.write("No timeline entries found.\n")
        sys.exit(1)

    # -------------------------------------------------------------------
    # Walk the pcap and compute outstanding over time.
    # -------------------------------------------------------------------
    sender_ip = "192.168.88.20"
    receiver_ip = "192.168.88.21"
    high_seq = 0      # includes SYN/FIN bytes when seen
    max_ack = 0
    # List of (timestamp_ns, outstanding) for later lookup
    outstanding_events = []

    # Regex to extract core fields
    pkt_re = re.compile(
        r"(?P<ts>\d+\.\d+) IP (?P<src_ip>\d+\.\d+\.\d+\.\d+)\.(?P<src_port>\d+) > "
        r"(?P<dst_ip>\d+\.\d+\.\d+\.\d+)\.(?P<dst_port>\d+): Flags \[(?P<flags>[^\]]+)\], (?P<rest>.*)"
    )
    seq_range_re = re.compile(r"seq (\d+):(\d+)")
    seq_single_re = re.compile(r"seq (\d+)(?:,|$)")
    ack_re = re.compile(r"ack (\d+)")

    for line in run_tcpdump(PCAP_PATH):
        m = pkt_re.search(line)
        if not m:
            continue
        ts_ns = ns_from_ts(m.group('ts'))
        src_ip = m.group('src_ip')
        dst_ip = m.group('dst_ip')
        flags = m.group('flags')
        rest = m.group('rest')

        # SYN from sender consumes one sequence number
        if src_ip == sender_ip and 'S' in flags and 'P' not in flags:
            # SYN (no payload range)
            m_seq = seq_single_re.search(rest)
            if m_seq:
                seq = int(m_seq.group(1))
                high_seq = max(high_seq, seq + 1)
        # FIN from sender also consumes one byte
        if src_ip == sender_ip and 'F' in flags:
            m_seq = seq_single_re.search(rest)
            if m_seq:
                seq = int(m_seq.group(1))
                high_seq = max(high_seq, seq + 1)
        # Data packets (sender → receiver) with payload range
        if src_ip == sender_ip and 'P' in flags:
            m_seq = seq_range_re.search(rest)
            if m_seq:
                seq_end = int(m_seq.group(2))  # end is exclusive
                high_seq = max(high_seq, seq_end)
        # ACKs from receiver – cumulative ack
        if src_ip == receiver_ip:
            m_ack = ack_re.search(rest)
            if m_ack:
                ack = int(m_ack.group(1))
                max_ack = max(max_ack, ack)

        outstanding = high_seq - max_ack
        if outstanding < 0:
            outstanding = 0
        outstanding_events.append((ts_ns, outstanding))

    # -------------------------------------------------------------------
    # For each pause, locate the first timestamp where outstanding == 0 after
    # the post_send of that pause.
    # -------------------------------------------------------------------
    output_lines = []
    for i in range(len(reps) - 1):
        rep = reps[i]
        next_rep = reps[i + 1]
        post_send = timeline[rep].get('post_send')
        app_sleep_start = timeline[rep].get('app_sleep_start')
        next_pre_send = timeline[next_rep].get('pre_send')
        if not (post_send and next_pre_send):
            continue
        # Find first event >= post_send where outstanding == 0
        zero_ts = None
        for ts, out in outstanding_events:
            if ts < post_send:
                continue
            if out == 0:
                zero_ts = ts
                break
        # Compute duration to next pre_send if zero observed
        duration = None
        if zero_ts is not None:
            duration = next_pre_send - zero_ts
        # Prepare line
        line = [
            str(i),
            str(post_send),
            str(app_sleep_start) if app_sleep_start is not None else "-",
            str(zero_ts) if zero_ts is not None else "-",
            str(next_pre_send),
            str(duration) if duration is not None else "-",
        ]
        output_lines.append('\t'.join(line))

    # Final pause (last rep) – no following pre_send
    last_rep = reps[-1]
    post_send = timeline[last_rep].get('post_send')
    app_sleep_start = timeline[last_rep].get('app_sleep_start')
    # Find zero after post_send (if any)
    zero_ts = None
    for ts, out in outstanding_events:
        if ts < post_send:
            continue
        if out == 0:
            zero_ts = ts
            break
    line = [
        str(last_rep),
        str(post_send),
        str(app_sleep_start) if app_sleep_start is not None else "-",
        str(zero_ts) if zero_ts is not None else "-",
        "-",
        "-",
    ]
    output_lines.append('\t'.join(line))

    # Header for readability
    header = "pause\tpost_send_ts\tapp_sleep_start_ts\tzero_ts\tnext_pre_send_ts\tduration_to_next_pre_send"
    print(header)
    for l in output_lines:
        print(l)


if __name__ == "__main__":
    analyze()
