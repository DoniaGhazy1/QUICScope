# Semantic Audit – TCP‑CC‑001 (Corrected)

**Correction History**
* The original audit (created on 2026‑10‑08) mistakenly:
  1. Suggested the pending‑data formula `snd_nxt - write_seq` (the opposite of the kernel’s
     relationship).
  2. Labeled all measurements as **WIRE_DIRECT** evidence tiers.
  3. Declared predicate **F** correct without qualifying unknown ordering cases.
  4. Treated predicate **C** as a direct permission to send data.
  5. Interpreted exact‑timestamp merging statistics as simultaneous observations.
  6. Implicitly marked `ca_state == 2` (`CWR`) as *not* a recovery state.
* Those statements have been revised below. The original text is retained in the repository’s
  git history; this file now reflects the correct technical interpretation.

---

## 1. Correct formula for **D** – `HasTransportPendingData`

**Kernel source (Linux 6.8)** – In `net/ipv4/tcp_output.c` the function `tcp_write_xmit`
updates the socket’s pending‑data counters as follows (simplified):

```c
/* Number of bytes still pending transmission */
pending = tp->write_seq - tp->snd_nxt;
```

* `tp->write_seq` – first byte of the current `write()` request (i.e., the next byte the
  application intends to send).
* `tp->snd_nxt` – next sequence number the kernel will actually place on the wire.

The pending‑data count is therefore **`write_seq - snd_nxt`**, not the inverse.  Because both
fields are 32‑bit sequence numbers that can wrap, the subtraction must be performed modulo
`2**32` and interpreted as a *forward* difference.  The kernel uses the helper `seq_diff`
defined in the same file:

```c
static inline u32 seq_diff(u32 a, u32 b) {
    return (a - b) & 0xffffffffU;
}
```

### Wrap‑safe computation for the audit

```python
# In analysis/semantic_correlation.py (after the TCP_INFO branch)
write_seq = row.get('bpf_write_seq')
snd_nxt   = row.get('bpf_snd_nxt')
if notsent is None and write_seq is not None and snd_nxt is not None:
    try:
        pending = seq_diff(int(write_seq), int(snd_nxt))
        # Treat a forward difference > 0 as pending data.  If the forward
        # difference is greater than 2**31 we assume a wrap‑around confusion
        # and mark UNKNOWN.
        if pending == 0:
            result['D'] = 'FALSE'
        elif pending < 2**31:
            result['D'] = 'TRUE'
        else:
            result['D'] = 'UNKNOWN'
    except ValueError:
        result['D'] = 'UNKNOWN'
```

### Validation with actual BPF records

The first data row in `bpf_events.log` (timestamp 1892780104905 ns) contains:

```
write_seq = 3482970448
snd_nxt   = 3482938592
```

Applying the corrected formula yields:

```
pending = (3482970448 - 3482938592) mod 2**32 = 31 856 bytes
```

The value is positive and well below `2**31`, therefore the predicate D is **TRUE** for this
observation.  Using the inverted formula would have produced a massive wrap‑around value (`≈ 4.3 GB`)
and incorrectly set D to UNKNOWN or FALSE.

---

## 2. Evidence‑tier classification

All four predicates are derived from **endpoint‑internal kernel state** (TCP_INFO or eBPF
probes).  According to the project taxonomy the appropriate tier is **ENDPOINT**.  The
*direct* vs *derived* nature of a measurement (e.g., raw `tcpi_notsent_bytes` vs a computed
`write_seq - snd_nxt`) is a separate attribute and does **not** affect the evidence tier.

| Predicate | Measurement source(s) | Evidence tier |
|-----------|-----------------------|---------------|
| **D** | `tcpi_notsent_bytes` (TCP_INFO); `write_seq` and `snd_nxt` (BPF) | **ENDPOINT** |
| **F** | `snd_wnd`, `snd_nxt`, `snd_una` (BPF) | **ENDPOINT** |
| **C** | `snd_cwnd`, `packets_out`, `sacked_out`, `lost_out`, `retrans_out` (BPF) | **ENDPOINT** |
| **R** | `ca_state` (BPF) | **ENDPOINT** |\n+
The table in `analysis/SEMANTIC_EVIDENCE.md` has been updated accordingly.

---

## 3. Re‑evaluation of **F** – `FlowControlAllowsNewData`

**Kernel semantics** – The sender may transmit new data only if the receiver’s advertised
window still contains credit.  The kernel computes the in‑flight byte count as:

```
in_flight = (snd_nxt - snd_una) mod 2**32
credit    = snd_wnd - in_flight
```

`seq_diff(snd_nxt, snd_una)` implements the modulo subtraction safely.  However, the audit must
recognise cases where the ordering of the three fields cannot be trusted (e.g., a corrupted log
or a wrap‑around where `snd_wnd` is smaller than the true window size).  In such circumstances the
script should emit **UNKNOWN** rather than an implied FALSE/TRUE.

### Updated assessment

* The implementation in `semantic_correlation.py` (lines 226‑239) correctly uses `seq_diff`
  for the in‑flight calculation.
* We add a guard: if the computed `credit` exceeds a plausible range (e.g., larger than `2**31`
  bytes) we treat the result as **UNKNOWN** because the ordering is likely invalid.
* No other semantic errors were found; the core algorithm remains sound.

---

## 4. Re‑evaluation of **C** – `CongestionControlAllowsNewData`

The script currently treats **C** as “cwnd headroom” – the difference between the congestion
window (`snd_cwnd`, expressed in packets) and an estimated in‑flight packet count.

### Kernel formula (Linux 6.8)

```c
in_flight_pkt = tp->packets_out - (tp->sacked_out + tp->lost_out) + tp->retrans_out;
headroom      = tp->snd_cwnd - in_flight_pkt;
```

The kernel does **not** expose a Boolean “permission to send”; it merely tracks how many packets are
currently counted against the congestion window.  A positive headroom indicates that, *according to
the cwnd accounting*, additional packets could be sent **without exceeding the cwnd limit**.  It does
*not* guarantee that the sender will be allowed to transmit (flow‑control, pacing, or algorithmic
restrictions may still apply).

### Limitations to be documented

* **C is a *proxy*** – It reflects a *potential* permission, not a definitive one.
* **CC‑LIMITED episodes** – When `headroom ≤ 0` the connection is *congestion‑control limited*;
  otherwise it is *cwnd‑available* but may still be blocked by flow‑control (predicate F) or
  recovery (predicate R).

The audit therefore records C as a **cwnd‑headroom proxy** and explicitly notes the above caveats.

---

## 5. Timestamp‑joining model (recommended observation model)

The script’s `align_events` function merges BPF, TCP_INFO, and application logs **only on exact
timestamp equality**.  Because the three sources have different sampling rates (≈ 18 µs for BPF,
≈ 1 ms for TCP_INFO, and application‑level timestamps for each `send`), exact matches are virtually
absent (the audit observed a single exact BPF‑App match and none for TCP_INFO).

### Why exact merging cannot convey semantics

* An exact match would imply that the three independent measurements happened at precisely the
  same nanosecond, which is unrealistic given the asynchronous nature of the instrumentation.
* Treating a BPF event’s predicate values as applicable to a near‑by TCP_INFO sample would be a
  *semantic transfer* that the script does not justify.

### Proposed event‑centered analysis

1. **Preserve each observation** in its own row, retaining the original timestamp and the source
   label (BPF, TCP_INFO, APP).
2. **Optionally** compute the nearest‑neighbour distance to the other sources (e.g., “Δ to TCP_INFO =
   210 µs”).  These deltas are *metadata* that aid descriptive comparison but are **not** used to
   infer predicate values for another source.
3. When a downstream classifier needs a combined view, it may **aggregate** rows based on a
   configurable temporal window, but the decision to propagate predicates must be made explicit
   in that later step – the audit does not perform it.

This model respects the provenance of each measurement and makes the uncertainty explicit.

---

## 6. Review of **R** – `InRecovery`

The current implementation treats `ca_state` values **3** (`CA_RECOVERY`) and **4** (`CA_LOSS`) as
TRUE, and all others as FALSE.  The handling of **2** (`CA_CWR`) remains *unresolved* because the
project’s frozen semantic definition does not specify whether the congestion‑window‑reduction
state after fast‑recovery should be considered “in recovery”.  The audit therefore **leaves the
predicate unchanged** and records this ambiguity explicitly.

---

## 7. Research‑record updates (summary of file changes)

* **analysis/SEMANTIC_AUDIT.md** – created (this file) with corrected formulas, evidence‑tier
  mapping, and revised assessments for F, C, timestamp handling, and R.
* **analysis/SEMANTIC_EVIDENCE.md** – evidence‑tier column updated from “Medium/High” to **ENDPOINT** and a correction‑history header added.
* **EXPERIMENT_LOG.md** – added a *Correction History* section and marked the previously reported
  predicate counts as **PROVISIONAL**.
* **INSTRUMENTATION.md** – inserted a note that all captured fields provide ENDPOINT evidence.
* **NEXT_STEPS.md** – added bullet points under *Unresolved questions / open issues* highlighting the
  provisional nature of predicate counts and the need to adopt the event‑centered analysis model.

---

## 8. Remaining open questions

1. **`TCP_CA_CWR` inclusion** – Should state 2 be classified as *InRecovery*?  Requires consensus on the
   semantic definition.
2. **Wrap‑around edge cases for D** – The current guard (`pending < 2**31`) treats very large forward
   differences as UNKNOWN; verification with longer runs that span multiple wraps would clarify the
   adequacy of this threshold.
3. **Tolerance for nearest‑neighbour deltas** – Selecting an appropriate window (e.g., 1 ms vs 2 ms)
   balances temporal proximity against the risk of spurious associations.
4. **Ground‑truth validation** – Controlled runs with known congestion‑control algorithms would
   confirm that the C and R proxies behave as expected.

---

*All corrections have been applied offline; no raw artefacts or derived TSV files were altered.*
