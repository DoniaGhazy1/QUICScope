#!/usr/bin/env python3
"""Summarize QUICScope exp1-support-audit native qlogs without changing them.

Usage: python3 scripts/summarize_runs.py
       python3 scripts/summarize_runs.py /path/to/exp1-support-audit

Writes reports/EXP1-B0/{qlog_files,event_counts,field_coverage,run_summary}.csv
and SUMMARY.md. Supports picoquic legacy JSON and qlog JSON-SEQ.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

EXP = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
RUNS = EXP / 'runs'
OUT = EXP / 'reports' / 'EXP1-B0'
OUT.mkdir(parents=True, exist_ok=True)

def read_qlog(path):
    if path.suffix == '.qlog':
        doc = json.loads(path.read_text())
        events = []
        for trace in doc.get('traces', []):
            for row in trace.get('events', []):
                if len(row) >= 4:
                    events.append({'name': f'{row[1]}:{row[2]}', 'data': row[3] or {}})
        return events, doc.get('qlog_version', 'unknown')
    objects = []
    with path.open(encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip().lstrip('\x1e').strip()
            if line:
                try:
                    objects.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise ValueError(f'{path}:{lineno}: {e}') from e
    header = next((o for o in objects if 'trace' in o), {})
    schema = ','.join(header.get('trace', {}).get('event_schemas', []))
    return [o for o in objects if 'name' in o], schema or header.get('qlog_version', 'unknown')

def write_csv(name, rows, columns):
    with (OUT / name).open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

def packet_ids(events, suffix):
    ids = set()
    for ev in events:
        if ev['name'].endswith(':' + suffix):
            data = ev.get('data', {})
            head = data.get('header', {})
            pn = head.get('packet_number')
            ptype = head.get('packet_type', data.get('packet_type'))
            if pn is not None:
                ids.add((ptype, pn))
    return ids

file_rows, event_rows, field_rows, summary_rows = [], [], [], []
per_run = defaultdict(dict)
for path in sorted(RUNS.rglob('*')):
    if not path.is_file() or path.suffix not in ('.qlog', '.sqlog'):
        continue
    endpoint = path.parent.name
    if endpoint not in ('client_qlog', 'server_qlog'):
        continue
    run = path.parent.parent
    run_rel = str(run.relative_to(EXP))
    stack = next((name for name in ('quic-go','picoquic','ngtcp2') if name in run.relative_to(RUNS).parts), 'unknown')
    events, schema = read_qlog(path)
    counts = Counter(e['name'] for e in events)
    fields = defaultdict(Counter)
    frame_counts = Counter()
    for e in events:
        for field in e.get('data', {}):
            fields[e['name']][field] += 1
        for frame in e.get('data', {}).get('frames', []):
            frame_counts[frame.get('frame_type', 'unknown')] += 1
    file_rows.append(dict(run=run_rel, stack=stack, endpoint=endpoint.replace('_qlog',''),
                          file=str(path.relative_to(EXP)), size_bytes=path.stat().st_size,
                          event_count=len(events), schema=schema))
    for name, n in sorted(counts.items()):
        event_rows.append(dict(run=run_rel, stack=stack, endpoint=endpoint.replace('_qlog',''), event=name, count=n))
    for name, fs in sorted(fields.items()):
        for field, n in sorted(fs.items()):
            field_rows.append(dict(run=run_rel, stack=stack, endpoint=endpoint.replace('_qlog',''), event=name, field=field, occurrences=n))
    per_run[run_rel][endpoint] = (events, path.stat().st_size, counts, frame_counts)

for rel, endpoints in sorted(per_run.items()):
    run = EXP / rel
    meta = {}
    if (run / 'metadata.txt').exists():
        for line in (run / 'metadata.txt').read_text().splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                meta[k] = v
    c = endpoints.get('client_qlog')
    s = endpoints.get('server_qlog')
    ssend = packet_ids(s[0], 'packet_sent') if s else set()
    crecv = packet_ids(c[0], 'packet_received') if c else set()
    csend = packet_ids(c[0], 'packet_sent') if c else set()
    srecv = packet_ids(s[0], 'packet_received') if s else set()
    slost = packet_ids(s[0], 'packet_lost') if s else set()
    # Fields intentionally describe logging, not actual on-wire packet loss.
    summary_rows.append(dict(run=rel, stack=meta.get('stack', next((n for n in ('quic-go','picoquic','ngtcp2') if n in Path(rel).parts), 'unknown')),
        payload_sha256=meta.get('payload_sha256', ''), validation=meta.get('validation','not-recorded'),
        rmem_default=meta.get('rmem_default','not-recorded'), rmem_max=meta.get('rmem_max','not-recorded'),
        client_qlog_bytes=c[1] if c else '', server_qlog_bytes=s[1] if s else '',
        server_packet_sent=len(ssend) if s else '', client_packet_received=len(crecv) if c else '',
        server_to_client_not_observed=len(ssend-crecv) if c and s else '',
        client_packet_sent=len(csend) if c else '', server_packet_received=len(srecv) if s else '',
        client_to_server_not_observed=len(csend-srecv) if c and s else '',
        server_packet_lost_events=(sum(n for name,n in s[2].items() if name.endswith(':packet_lost')) if s else ''),
        server_packet_dropped_events=(sum(n for name,n in s[2].items() if name.endswith(':packet_dropped')) if s else ''),
        client_event_count=len(c[0]) if c else '', server_event_count=len(s[0]) if s else '',
        server_data_blocked_frames=s[3].get('data_blocked',0) if s else '',
        server_stream_data_blocked_frames=s[3].get('stream_data_blocked',0) if s else ''))

summary_columns = ['run','stack','validation','payload_sha256','rmem_default','rmem_max','client_qlog_bytes','server_qlog_bytes','server_packet_sent','client_packet_received','server_to_client_not_observed','client_packet_sent','server_packet_received','client_to_server_not_observed','server_packet_lost_events','server_packet_dropped_events','client_event_count','server_event_count','server_data_blocked_frames','server_stream_data_blocked_frames']
write_csv('qlog_files.csv', file_rows, ['run','stack','endpoint','file','size_bytes','event_count','schema'])
write_csv('event_counts.csv', event_rows, ['run','stack','endpoint','event','count'])
write_csv('field_coverage.csv', field_rows, ['run','stack','endpoint','event','field','occurrences'])
write_csv('run_summary.csv', summary_rows, summary_columns)

candidate = {'quic-go':'20261110T173944Z-3540','picoquic':'20261110T173947Z-3621','ngtcp2':'20261110T173950Z-3680'}
chosen = {r['stack']:r for r in summary_rows if any(r['run'].endswith('/'+rid) for rid in candidate.values())}
lines = [
    '# EXP1-B0 — Generated qlog audit summary',
    '',
    'Generated from files under `runs/` by `scripts/summarize_runs.py`. Do not edit generated tables manually.',
    'Source qlogs and their original schema/event names are preserved. An absent event means **not observed**, not unsupported.',
    '',
    '## Candidate common-workload baseline (4 MiB receive buffers)',
    '',
    '| Stack | Run ID | Client qlog (B) | Server qlog (B) | Server sent | Client received | Missing S→C | Server loss events | Server drop events |',
    '|---|---|---:|---:|---:|---:|---:|---:|---:|',
]
for stack in ('quic-go','picoquic','ngtcp2'):
    r = chosen.get(stack)
    if not r:
        lines.append(f'| {stack} | NOT FOUND | | | | | | | |')
    else:
        lines.append('| ' + ' | '.join(str(x) for x in (stack, candidate[stack], r['client_qlog_bytes'],r['server_qlog_bytes'],r['server_packet_sent'],r['client_packet_received'],r['server_to_client_not_observed'],r['server_packet_lost_events'],r['server_packet_dropped_events']))+' |')
lines += ['', '## Interpretation limits', '',
          '- Cross-endpoint packet-number comparisons are consistency checks between endpoint logs, not an independent wire oracle.',
          '- `packet_dropped` and `packet_lost` have different meanings.',
          '- Event names and field semantics vary across the versions declared by the implementations.',
          '- Socket-buffer values in metadata describe host sysctls, not verified effective socket buffer allocations.',
          '- Reconstructed historical observations from interactive terminals belong in `TERMINAL_OBSERVATIONS.md`, not the generated CSVs.',
          '', '## Other generated tables', '',
          '- `run_summary.csv`: every discovered run with packet correspondence and qlog sizes.',
          '- `qlog_files.csv`: native schemas, endpoint roles, bytes, and event totals.',
          '- `event_counts.csv`: occurrences by exact native event name per endpoint/run.',
          '- `field_coverage.csv`: occurrences of exact top-level data fields by event (not a semantic equivalence assertion).', '']
(OUT/'SUMMARY.md').write_text('\n'.join(lines), encoding='utf-8')
print(f'Analyzed {len(file_rows)} qlog files across {len(summary_rows)} runs.')
for name in ('SUMMARY.md','run_summary.csv','qlog_files.csv','event_counts.csv','field_coverage.csv'):
    print(OUT/name)
