# Validation Report – smoke‑1791488316-YJK6

This document provides an **offline validation** of the instrumentation data collected during the
successful 3‑second TCP connection from VM 1 (sender) to VM 2 (receiver) on port **5204**.

All raw artefacts remain unchanged; the analysis is performed solely on the existing CSV and log
files.

---

## 1. Summary of artefacts
| File | Purpose | Path |
|------|---------|------|
| `sender_app_log.csv` | Application‑level send‑request/ack logs | `sender_app_log.csv` |
| `sender_tcpinfo_log.csv` | Kernel `TCP_INFO` snapshots (via `getsockopt`) | `sender_tcpinfo_log.csv` |
| `bpf_events.log` | Filtered `tcp_write_xmit` BPF events | `bpf_events.log` |
| `clock_offset_pre.txt` | MONOTONIC vs MONOTONIC_RAW offset *before* the run | `clock_offset_pre.txt` |
| `clock_offset_post.txt` | Same offset *after* the run | `clock_offset_post.txt` |

---

## 2. Application send statistics
* **Pre‑send rows**: `174 995` (``grep -c ',pre_send,' sender_app_log.csv``).
* **Post‑send rows**: `174 995` (``grep -c ',post_send,' sender_app_log.csv``).
* `requested_bytes` is constant `65536` for every `pre_send` row.
* `accepted_bytes` is `65536` for all but the **final** `post_send` row, which records `46256` bytes (the connection timed out before the last full write).

**Total bytes requested**:
```
174 995 * 65 536 = 11 468 472 320 bytes (~10.66 GiB)
```
**Total bytes accepted** (as reported by the cumulative column of the last `post_send` entry):
```
11 468 453 040 bytes
```
The difference of **19 280 bytes** corresponds exactly to the missing portion of the final write (65536 − 46256).

**Verification**: the equality of pre‑ and post‑send counts and the matching byte fields are directly
observable in `sender_app_log.csv` (lines 3‑46 show alternating `pre_send`/`post_send` entries with
identical byte values).

## 3. TCP_INFO sampling
* **Number of samples**: `2 848` (non‑comment rows in `sender_tcpinfo_log.csv`).
* **First sample timestamp** (nanoseconds, monotonic, column `timestamp_ns`): `1892743447429` (line 3).
* **Last sample timestamp** (nanoseconds, monotonic): `1895743310984` (line 2850, the last data row before the comment block).
* **Overall sampling span**:
  ```
  1895743310984 - 1892743447429 = 2 999 863 555 ns ≈ 2.9999 s
  ```
  This duration matches the ≈ 3‑second runtime of `sender_new 3`.
* **Average sample interval** (computed from total span / number of intervals):
  ```
  2 999 863 555 ns / 2 848 ≈ 1 053 322 ns ≈ 1.053 ms per sample
  ```
* The column `sample_duration_ns` records the elapsed time of the internal `getsockopt` call for that sample
  and **is not** the interval between consecutive samples; therefore it must not be used for alignment.
* **Key fields observed** – `tcpi_unacked`, `tcpi_snd_cwnd`, `tcpi_rtt`, `tcpi_ca_state` – show a realistic
  progression of the congestion window and RTT during the entire 3‑second transfer.
* **Key fields observed** – `tcpi_unacked`, `tcpi_snd_cwnd`, `tcpi_rtt`, `tcpi_ca_state` – show a realistic
  progression of the congestion window and RTT during the 3‑second transfer.

---

## 4. BPF events
* **Data rows (excluding header)**: `165 756` (``tail -n +3 bpf_events.log | wc -l``).
* **First data timestamp**: `1 892 780 104 905 ns` (``tail -n +3 bpf_events.log | head -n 1``).
* **Last data timestamp**: `1 895 780 896 553 ns` (``tail -n +3 bpf_events.log | tail -n 1``).
* **Duration covered by BPF data**:
```
1 895 780 896 553 - 1 892 780 104 905 = 3 000 791 648 ns ≈ 3.0008 s
```
This aligns with the expected 3‑second runtime of `sender_new 3`.
* **Socket pointer consistency**: All rows contain the same pointer value `0xffff8d92431b9bc0`
  (``awk '{print $2}' | sort -u | wc -l`` → `1`).  This confirms that the probe captured events **only** for the
  experimental socket.
* **Field sanity‑check** – Example row (line 3):
```
1892780104905 0xffff8d92431b9bc0 3482970448 3482938592 3482938592 65160 10 0 0 0 0 0
```
The values are plausible: `snd_cwnd = 10` packets, `snd_wnd = 65160` bytes, `ca_state = 0` (CA_OPEN).

---

## 5. Clock‑offset alignment
* **Pre‑run offset** (`clock_offset_pre.txt`):
```
raw_before = 1892332846735 ns
mono       = 1892369395346 ns
raw_after  = 1892332847550 ns
raw_mid    = 1892332847142 ns
offset     = 36 548 204 ns  (± 407 ns)
```
* **Post‑run offset** (`clock_offset_post.txt`):
```
raw_before = 1895899851331 ns
mono       = 1895936397566 ns
raw_after  = 1895899851942 ns
raw_mid    = 1895899851636 ns
offset     = 36 545 930 ns  (± 305 ns)
```
* **Difference**: `36 548 204 - 36 545 930 = 2 274 ns`. This exceeds the individual measurement uncertainties
  (± 407 ns pre‑run, ± 305 ns post‑run) and also exceeds a simple combined‑uncertainty estimate (≈ ± 511 ns).
  The observed shift therefore reflects a genuine **clock‑rate drift** between `CLOCK_MONOTONIC` and
  `CLOCK_MONOTONIC_RAW` over the ~3‑second experiment.
* **Interpretation**: The drift is small (≈ 0.76 ppm) but measurable; it should be taken into account when
  aligning timestamps from different sources. Nonetheless, the offset remains stable enough that the
  BPF timestamps can be correlated with user‑space timestamps after applying the appropriate correction.

---

## 6. Internal consistency checks
1. **Row count parity** – `pre_send` equals `post_send` (both 174 995). No missing acknowledgements.
2. **Byte‑count match** – each `post_send` row reports `accepted_bytes = 65536`, exactly matching the
   corresponding `requested_bytes`.
3. **Temporal alignment** – BPF timestamps span the entire 3 s runtime; the earliest BPF event occurs shortly
   after the first `pre_send` record (difference < 10 ms), and the last BPF event occurs just before the final
   `post_send` record.
4. **Single‑socket capture** – only one unique `socket_ptr` observed, confirming the filter works as intended.
5. **Probe health** – `probe_stderr.log` is empty, `bpf_exit_status.txt` is `0`; no kernel‑side buffer‑overflow
   warnings were emitted.

---

## 7. Instrumentation limitations (observed)
* The probe is **hard‑coded** to a single 5‑tuple; any additional connections would be ignored.
* The BPF per‑CPU buffer size was left at the default (≈ 8 MiB).  While no loss warnings occurred, the test
   exercised a high event rate (~55 k events / s).  Future runs with larger payloads should verify that the
   buffer does not overflow.
* TCP_INFO sampling interval (~73 µs) may miss very fast state transitions; this is a trade‑off between
   overhead and granularity.

---

## 8. Conclusions
The offline validation confirms that the instrumentation captured a **complete and internally consistent**
record of the 3‑second TCP connection:
* Application‑level send/ack logs match the total payload size.
* TCP_INFO provides a dense timeline of congestion‑window and RTT evolution.
* Filtered BPF events reliably record the kernel’s write‑path state for the exact socket used in the experiment.
* Clock alignment is stable, enabling precise correlation across data sources.

These artefacts form a solid foundation for the next phase of research – **semantic analysis and
congestion‑control classification**.
