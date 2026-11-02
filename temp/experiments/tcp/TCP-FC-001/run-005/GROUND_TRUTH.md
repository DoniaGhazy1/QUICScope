# TCP-FC-001 run-005 – Frozen Ground‑Truth Evidence

## Verification steps

1. **Read `sender_timeline.csv`** – located the pre_send and post_send rows:
   - `1791409208771441545,pre_send,65536,,,1179648`
   - `1791409209073288466,post_send,,65536,301846921,1245184`
2. **Extract raw TCP window advertisements** from `capture.pcap` (via `tcpdump`):
   - First zero‑window packet: `1791409208853555000 ns`
   - Last  zero‑window packet: `1791409209065246000 ns`
   - First positive window after zero: `1791409209072252000 ns`
3. **Extract renewed data progress** (ACK with increased sequence) from pcap:
   - First renewed new‑data high‑water: `1791409209072739000 ns` (ACK 380 829)
4. **Verify numeric values** – used Bash arithmetic to confirm durations:
   - `first‑zero → first‑positive = 218 697 000 ns`
   - `first‑zero → renewed‑progress = 219 184 000 ns`
   - `send() duration = 301 846 921 ns`
   - `send() start precedes first zero‑window by 82 113 455 ns`
   - `send() end follows first positive window by 1 036 466 ns`
5. **Read `receiver_timeline.csv`** – confirmed stationary high‑water before/through the zero‑window:
   - High‑water at start of zero‑window: `373 376 bytes` (ACK 373 377)
   - Renewed high‑water after window reopens: `380 828 bytes` (ACK 380 829)
   - Progress increase: `7 452 bytes`
6. **Checked `PASSIVE‑ANALYSIS.md`** – it already reports the same timestamps, durations, and the 2710 negative‑credit anomalies.

All values match the expected ones presented in the prompt.

## Evidence table

| Event                               | Timestamp (ns)      | Relative time (ns)¹ | Observable (pcap)                                 | Semantic meaning |
|------------------------------------|---------------------|---------------------|---------------------------------------------------|------------------|
| `send()` begins (pre_send)         | 1791409208771441545| –0 – (reference)    | `pre_send` row in `sender_timeline.csv`           | Sender starts a 64 KiB write |
| First zero‑window advertisement    | 1791409208853555000| +82 113 455         | ACK with `win 0` (src 192.168.88.21 → dst 192.168.88.20) | Receiver credit closed |
| Last zero‑window advertisement     | 1791409209065246000| +293 804 455        | ACK with `win 0`                                   | Credit remains zero |
| First positive‑window advertisement| 1791409209072252000| +300 810 455        | ACK with `win 31796` (raw)                         | Receiver credit reopens |
| First renewed new‑data high‑water  | 1791409209072739000| +301 297 455        | ACK with increased ACK number (380 829)            | Data progress resumes |
| `send()` returns (post_send)       | 1791409209073288466| +301 846 921        | `post_send` row in `sender_timeline.csv`          | Sender’s write completes |

¹ Relative time is measured from the start of the `send()` (pre_send).

## Phase assessment table

| Phase | Wire evidence | Endpoint evidence | Progress evidence | Verdict |
|------|---------------|-------------------|-------------------|---------|
| A    | Positive advertised window (initial) | `SO_RCVBUF = 65536` reported as 131072 bytes | Receiver reads data, cumulative bytes increase | **SUFFICIENT** |
| B    | Zero‑window packets (two ACKs with `win 0`) | Sender’s `send()` call spans the whole zero‑window interval | High‑water stays at 373 376 bytes throughout | **SUFFICIENT** |
| C    | Positive‑window packet (`win 31796`) then ACK with increased sequence | Receiver advertises credit again before data advances | High‑water jumps to 380 828 bytes (+7 452 bytes) | **SUFFICIENT** |

## Frozen classification

**A. VALID A→B→C PASSIVE FC TRANSITION**

## Why this is receiver flow‑control rather than congestion loss

* The receiver explicitly advertised a **zero TCP window** (two ACKs with `win 0`), closing all receive credit.
* While the window was zero, the **sender’s new‑data high‑water remained stationary** at 373 376 bytes – no new data was acknowledged.
 * A **blocking `send()`** call started before the credit closed and stayed outstanding for the entire zero‑window interval (301.847 ms), providing controlled endpoint evidence that the sender continued attempting to supply data while receiver credit was closed.
* Data progress only resumed **after the receiver advertised a positive window** and the first renewed ACK advanced the high‑water mark, demonstrating that the stall was directly caused by the receiver’s credit exhaustion rather than any loss or congestion signal.

## Measurement caveat

The negative reconstructed-credit samples are consistent with limitations of reconstructing sender‑internal SND.NXT/SND.UNA/SND.WND from an endpoint‑near capture, particularly in the presence of TSO/GSO/offload. Their exact cause is not established.

Phase B does not depend on negative reconstructed‑credit values. Its critical evidence is:
* raw TCP Window == 0 (WIRE_DIRECT)
* stationary observed new‑data high‑water
* blocking `send()` outstanding across the interval
* subsequent positive‑window reopening
* subsequent renewed new‑data progress after reopening
* absence of obvious passive loss/congestion evidence during the candidate stall

---

**All raw values have been independently verified against the experiment artifacts.**
The frozen ground‑truth file is located at:

```
/home/rosa/experiments/tcp/TCP-FC-001/run-005/GROUND_TRUTH.md
```

`PASSIVE-ANALYSIS.md` and this frozen artifact agree on every timestamp, duration, and classification.

Final verdicts: Phase A = SUFFICIENT, Phase B = SUFFICIENT, Phase C = SUFFICIENT.

The experiment **TCP‑FC‑001** can now be marked **VALIDATED** with canonical run **run‑005** and classification **A. VALID A→B→C PASSIVE FC TRANSITION**.
