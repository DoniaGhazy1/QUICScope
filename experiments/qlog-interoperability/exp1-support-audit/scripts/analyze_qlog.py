#!/usr/bin/env python3

"""
Simple qlog analyzer for Experiment 1.

The script reads a qlog file (JSON Text Sequence) and extracts a list of
event names with their timestamps.  It writes a CSV file with columns:
    timestamp,event_name,fields_json
Only fields present in the event are included as a JSON‑encoded string.
The output can be used to fill the support‑matrix and field‑matrix CSVs.

Usage:
    python3 analyze_qlog.py <input_qlog> <output_csv>

If the input file does not exist or is empty, an empty CSV with just the
header row is written.
"""

import sys
import json
import csv
from pathlib import Path

def parse_qlog(qlog_path: Path):
    """
    Parse a qlog JSON‑SEQ file. Each line is a separate JSON object.
    Returns a list of (timestamp, event_name, fields_dict).
    """
    events = []
    if not qlog_path.is_file():
        return events
    with qlog_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines but keep processing the rest
                continue
            # The qlog spec can wrap events under "traces" → "events",
            # but many implementations output a flat sequence.
            if obj.get("name") == "trace":
                continue
            if "name" in obj and "data" in obj:
                timestamp = obj.get("relative_time") or obj.get("time")
                event_name = obj["name"]
                fields = obj["data"]
                events.append((timestamp, event_name, fields))
    return events

def write_csv(events, csv_path: Path):
    with csv_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["timestamp", "event_name", "fields_json"])
        for ts, name, fields in events:
            writer.writerow([ts, name, json.dumps(fields, separators=(",", ":"))])

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input_qlog> <output_csv>", file=sys.stderr)
        sys.exit(1)
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    events = parse_qlog(input_path)
    write_csv(events, output_path)
    print(f"Analyzed {len(events)} events from {input_path} → {output_path}")

if __name__ == "__main__":
    main()