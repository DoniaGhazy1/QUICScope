# Research Checkpoint 004 – Correction Note

## Verified historical results (from prior work)

- **Standard‑header integrity** – `/usr/include/stddef.h` is a manual stub, not used by the compiler; its removal does not affect the build.
- **Isolated clean‑build status** – Building with the `boringssl-boring-crate` feature succeeds, while the default feature set fails due to missing BoringSSL symbols.
- **qlog timestamp semantics (Quiche 0.20.2)** – `packet_sent.time` is the event timestamp; `packet_sent.send_at_time` is the internal generation timestamp, **not** the kernel‑enforced transmission deadline. The internal deadline lives in `SendInfo.at` and is **not** emitted in the qlog.
- **Verified socket‑send execution path & pacing status (0.20.2)** – `SO_TXTIME` is set successfully, GSO detection succeeds, and the code path `send_to_gso_pacing` (via `apps/src/sendto.rs`) is exercised.
- **Baseline trace findings (0.20.2)** – `packet_sent.send_at_time` appears for all packets; fields such as `pacing_deadline`, `intended_release_time_ms`, and `socket_send_time_ms` are absent; recovery metrics are present.

## Invalid claims about Quiche 0.30.0 (and their correction)

| Claim | Status | Evidence (official upstream source) |
|-------|--------|--------------------------------------|
| Quiche 0.30.0 adds `intended_release_time_ms` and `socket_send_time_ms` fields to `PacketSent`. | **INVALID** | The `PacketSent` struct in `qlog/src/events/quic.rs` (commit `07671779deada0655d99b2b6ea3d87329242b0d3`, tag `0.30.0`, lines 803‑821) contains only `send_at_time` among timing fields – no `intended_release_time_ms` or `socket_send_time_ms`. |
| `SendInfo` uses a field named `release`. | **INVALID** | The `SendInfo` struct in `quiche/src/lib.rs` (same commit, lines 516‑528) defines a field `pub at: Instant;` – there is **no** `release` field. |
| A CLI flag `--pacing-mode` exists in the server binary. | **INVALID** | Argument parsing in `apps/src/args.rs` (lines 470‑490) defines `--disable-pacing` only. No `--pacing-mode` flag is present. |
| qlog emits `pacer_update` / `pacer_set` events. | **INVALID** | A full‑text search of the `qlog` crate (`qlog/src/`) under the same commit finds **no** definitions of `pacer_update` or `pacer_set`. The only pacing‑related field in `PacketSent` is `send_at_time`. |

## Summary

All previously verified observations remain correct. The above‑listed claims about additional fields, CLI options, and qlog events in Quiche 0.30.0 are **unsupported** by the official upstream source at commit `07671779deada0655d99b2b6ea3d87329242b0d3`.

The research direction can now shift to assessing the diagnostic capabilities already defined in the **July 2026 IETF qlog specification** (blocking reasons, data‑movement events, UDP datagram submission, and recovery metrics) without further modifications to Quiche or additional experiments.
