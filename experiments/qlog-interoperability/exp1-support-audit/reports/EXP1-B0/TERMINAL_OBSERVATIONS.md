# EXP1-B0 — Terminal observations and experimental interventions

**Source:** Reconstructed from the operator's terminal outputs shared in the QUICScope research conversation on 2026-11-10. This is an annotated record, **not** a verbatim terminal-session capture. Unreported measurements are explicitly marked *not measured*. Raw qlogs and logs should remain in `runs/`; generated tables should come from `scripts/summarize_runs.py`.

## Common workload and verification

- Application workload: HTTP/3 `GET /payload.bin`, from server to client on localhost.
- Reference file size: **1,048,576 bytes (1 MiB)**.
- Reference SHA-256: `9bf9f0415bf644a419988c10cfa2e6bd089a16a207feef0f8420e66ebedf17f8`.
- Successful runs were checked with `cmp`; the verification wrapper also retained qlogs from both endpoints.
- Pinned upstream commits: quic-go `ed90516797ec8ed7314c2b163797eca58fd5a2b8`; ngtcp2 `e82176c8105490eeedb1ee1c805578d9ea867672`; picoquic `77fa50201a2897a1aa90f9d0ff43e8d2fd39d182`.
- Note: Commit hashes alone are not sufficient binary provenance, particularly for the earlier locally modified quic-go checkout.

## Historical interventions and results

| Condition | Representative run | Host rmem_default / rmem_max | GSO | Server packets sent | Client packets received | Server packet_lost events | UdpRcvbufErrors delta | Payload |
|---|---|---:|---|---:|---:|---:|---:|---|
| ngtcp2 original | `20261110T160318Z-74415` | 212,992 / 212,992 B | Default | 880 | 761 | 119 | Not measured | PASS |
| ngtcp2 repeat | `20261110T171601Z-1701` | 212,992 / 212,992 B | Default | 880 | 761 | 119 | +4 | PASS |
| ngtcp2 no-GSO | `20261110T172332Z-2186` | 212,992 / 212,992 B | Disabled on client and server | 924 | 762 | 162 | +162 | PASS |
| ngtcp2 larger buffer | `20261110T172657Z-2455` | 4,194,304 / 4,194,304 B | Default | 761 | 761 | 0 | 0 | PASS |
| ngtcp2 larger-buffer repetition 1 | `20261110T172944Z-2696` | 4,194,304 / 4,194,304 B | Default | 761 | 761 | 0 | 0 | PASS |
| ngtcp2 larger-buffer repetition 2 | `20261110T173017Z-2823` | 4,194,304 / 4,194,304 B | Default | 760 | 760 | 0 | 0 | PASS |
| ngtcp2 larger-buffer repetition 3 | `20261110T173050Z-2928` | 4,194,304 / 4,194,304 B | Default | 761 | 761 | 0 | 0 | PASS |

### ngtcp2 original-loss analysis

The first original run's server recorded **119 distinct** 1-RTT `quic:packet_lost` events; these 119 packet numbers were among sender-recorded sent packets and absent from client-recorded received packets. Sender send timestamps ranged **10–13 ms** and loss-declaration timestamps **14–16 ms** in the relative qlog time scale. All 119 missing packets contained a STREAM frame, representing **165,840 bytes of logged STREAM-frame length** (not necessarily unique application data).

Four contiguous missing packet-number ranges in the first run:

- `866338887..866338925` — 39 packets
- `866338927..866338932` — 6 packets
- `866339024..866339081` — 58 packets
- `866339172..866339187` — 16 packets

When normalized to the first sent server 1-RTT packet number, the two default-GSO runs had **118 of 119** missing positions in common. This supports a repeatable mechanism rather than independent random loss, but does not by itself identify the drop point.

### Kernel UDP counter snapshots

| Condition | `UdpInDatagrams` before → after | `UdpInErrors` before → after | `UdpRcvbufErrors` before → after | `UdpSndbufErrors` |
|---|---|---|---|---|
| ngtcp2 default-GSO repeat | 209 → 258 | 0 → 4 | 0 → 4 | 0 → 0 |
| ngtcp2 no-GSO | 306 → 1088 | 4 → 166 | 4 → 166 | 0 → 0 |
| ngtcp2 first enlarged-buffer run | 1122 → 1170 | 166 → 166 | 166 → 166 | 0 → 0 |
| Three further enlarged-buffer trials | Not recorded in provided output | 166 → 166 each trial | 166 → 166 each trial | 0 → 0 each trial |

**Interpretation:** Increasing `net.core.rmem_default` and `net.core.rmem_max` from **212,992 B** to **4,194,304 B** coincided with zero kernel UDP receive-buffer errors and zero sender-side qlog loss declarations for **four** ngtcp2 trials. This is strong evidence that the default host receive-buffer capacity contributed to the anomalous result for this workload. Kernel counters are host-wide; neither per-socket allocation nor independent capture-level packet correspondence has been established. The original settings were restored after the intervention.

## Picoquic packet-logging limit

`picoquicdemo -h` reported: `-L  Log all packets. If absent, log stops after 100 packets.`

- Before `-L`: sample server log recorded **102** `transport:packet_sent` events, versus **752** client `transport:packet_received` events.
- With `-L` on **both endpoints**, run `20261110T173836Z-3279` recorded server-sent **752**, client-received **752**, server-received **29**, client-sent **29**, while the 1 MiB payload verification passed.
- Final candidate run `20261110T173947Z-3621` likewise recorded **752/752** and **29/29**.
- The final candidate picoquic server emitted one `transport:packet_dropped` event: `{"packet_size":780,"trigger":"padding_packet"}`. The event's cause at the source-code level remains unverified. It is **not** a `packet_lost` event and is not, by itself, evidence of application-data loss.
- An earlier picoquic validation run attempted resumption/0-RTT after loading a stored ticket. Later runner validations used a new per-run ticket path. Full handshake/0-RTT exclusion still warrants trace-level verification.

## Candidate frozen common-workload baseline (4 MiB host buffer)

| Stack | Run | Client qlog bytes | Server qlog bytes | Server sent / client received | Client sent / server received | Server packet_lost events | Server packet_dropped events |
|---|---|---:|---:|---|---|---:|---:|
| quic-go | `20261110T173944Z-3540` | 285,428 | 401,097 | 840 / 840 | 45 / 45 | 0 | 0 |
| picoquic | `20261110T173947Z-3621` | 306,878 | 365,592 | 752 / 752 | 29 / 29 | 0 | 1 (`padding_packet`) |
| ngtcp2 | `20261110T173950Z-3680` | 320,934 | 321,365 | 762 / 762 | 19 / 19 | 0 | 0 |

All candidate runs: client exit status 0, same reference checksum, `rmem_default=rmem_max=4194304`, native client/server qlogs present. **Important:** Cross-endpoint qlog packet-number correspondence is a logging consistency check, not a wire-level packet-delivery oracle. The stacks have not yet been made equivalent in CC/FC transport parameters; qlog schema/event equivalence has also not been established.

## Original qlog schema observations

- quic-go: sequential qlog, QUIC event schema `urn:ietf:params:qlog:events:quic-12`, HTTP/3 event schema `...:http3-12`.
- ngtcp2: sequential qlog, QUIC event schema `urn:ietf:params:qlog:events:quic-14`.
- picoquic: legacy JSON qlog with `qlog_version: draft-00` and event arrays.

Do **not** infer source-level support from a baseline event's absence. Normalize cautiously and always preserve raw field names, units, and schema metadata.

## Missing verbatim transcript and future capture

This record is built from terminal output pasted in the research conversation; it is not a full terminal transcript. Some past terminal stdout was not saved in process log files, and shell history alone does not recover command output. For subsequent sessions, use `script -q -f -a reports/EXP1-B0/terminal_session.typescript` in an interactive terminal (after creating the directory), then `exit` to stop recording. Avoid capturing passwords, tokens, keys or other secrets. The runner's `client.log` and `server.log` also preserve process-level output.
