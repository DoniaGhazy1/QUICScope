# Instrumentation – TCP‑CC‑001

The project uses a **filtered `tcp_write_xmit` eBPF probe** to capture kernel‑level TCP state
information that is relevant for congestion‑control classification.  The design deliberately
limits the probe to a single socket (the experimental 5‑tuple) to keep the data volume tractable
and to avoid interference with unrelated traffic.

---

## 1. Probe script location
```
/home/rosa/experiments/tcp/TCP-CC-001/monitor/smoke-001/tcp_write_xmit_filtered.bt
```
The script is invoked with `sudo bpftrace -o <logfile> <script>`.

---

## 2. Filtering logic (socket‑tuple)

```c
BEGIN {
    printf("timestamp_ns socket_ptr write_seq snd_nxt snd_una snd_wnd snd_cwnd packets_out sacked_out lost_out retrans_out ca_state\n");
}

kprobe:tcp_write_xmit
{
    $sk = (struct sock *)arg0;
    // NOTE: kernel stores IPs and ports in **network byte order** (big‑endian).
    // The experiment constants are written in **little‑endian** so they match the value
    // seen by the kernel after the implicit byte‑swap.
    //   192.168.88.20  => 0x1458A8C0
    //   192.168.88.21  => 0x1558A8C0
    //   port 5204      => 0x5414
    if ($sk->__sk_common.skc_rcv_saddr == 0x1458A8C0 &&
        $sk->__sk_common.skc_daddr    == 0x1558A8C0 &&
        $sk->__sk_common.skc_dport    == 0x5414) {
        $tp   = (struct tcp_sock *)$sk;
        $icsk = (struct inet_connection_sock *)$sk;
        printf("%lld %p %u %u %u %u %u %u %u %u %u %u\n",
               nsecs,
               $sk,
               $tp->write_seq,
               $tp->snd_nxt,
               $tp->snd_una,
               $tp->snd_wnd,
               $tp->snd_cwnd,
               $tp->packets_out,
               $tp->sacked_out,
               $tp->lost_out,
               $tp->retrans_out,
               $tp->ca_state);
    }
}
```

### 2.1 Endian considerations
* The kernel fields `skc_rcv_saddr`, `skc_daddr`, and `skc_dport` contain **network‑order** values.
* The script compares them against **host‑order** literals written in little‑endian form (`0x1458A8C0` etc.).
* This approach was verified by inspecting the resulting BPF log – the filter correctly captured
  events only for the experimental connection.

---

## 3. Captured BPF fields and semantics

| Field | Description |
|-------|-------------|
| `timestamp_ns` | Kernel monotonic timestamp (nanoseconds) at probe entry. |
| `socket_ptr`   | Kernel pointer to the `struct sock` – serves as a unique identifier for the socket. |
| `write_seq`    | TCP sequence number of the first byte in the current write call. |
| `snd_nxt`      | Next sequence number to be sent (high‑water mark). |
| `snd_una`      | Oldest un‑acknowledged sequence number (send‑un‑acknowledged). |
| `snd_wnd`      | Advertised send window (in bytes). |
| `snd_cwnd`     | Congestion window (in packets). |
| `packets_out`  | Number of packets transmitted on the socket. |
| `sacked_out`   | Number of SACKed packets. |
| `lost_out`     | Number of lost packets reported by the kernel. |
| `retrans_out`  | Number of retransmitted packets. |
| `ca_state`     | Current congestion‑avoidance state (e.g., `CA_OPEN`, `CA_DISORDER`, etc.). |

### 3.1 Probe placement semantics

The `kprobe:tcp_write_xmit` attached by the BPF script triggers **on function entry**, before any of the internal logic that checks the congestion‑window (`snd_cwnd`) or the receiver‑window (`snd_wnd`). This is evident from the Linux 6.8 source (see `net/ipv4/tcp_output.c`): the probe is placed at the very beginning of `tcp_write_xmit`, and the subsequent checks (`tcp_cwnd_test`, `tcp_snd_wnd_test`, etc.) occur later in the function body. Consequently, the probe records the kernel state **prior** to any early‑exit decisions, and therefore does **not** indicate which branch (e.g., flow‑control limited vs congestion‑control limited) was taken. The observed predicates are thus derived from the snapshot of kernel fields at entry, not from the outcome of the internal checks.

---

#### 3.2 Kernel source excerpt – `tcp_write_xmit` entry

Below is the beginning of the `tcp_write_xmit` function (Linux 6.8, `net/ipv4/tcp_output.c`, lines 2700‑2714).  The `kprobe:tcp_write_xmit` fires **at function entry**, before any of the early checks that enforce `snd_cwnd` or `snd_wnd` limits.

```c
static bool tcp_write_xmit(struct sock *sk, unsigned int mss_now, int nonagle,
                           int push_one, gfp_t gfp)
{
    struct tcp_sock *tp = tcp_sk(sk);
    struct sk_buff *skb;
    unsigned int tso_segs, sent_pkts;
    int cwnd_quota;
    int result;
    bool is_cwnd_limited = false, is_rwnd_limited = false;
    u32 max_segs;

    sent_pkts = 0;

    tcp_mstamp_refresh(tp);
    // Early MTU probing and other checks follow …
```

These lines demonstrate that the probe captures the values of `snd_cwnd`, `snd_wnd`, `snd_nxt`, etc., **before** any conditional logic that might limit transmission based on those fields.

## 4. Clock alignment – MONOTONIC vs MONOTONIC_RAW

To correlate BPF timestamps with user‑space timestamps (e.g., the `sender_new` CSV logs) we
measure the offset between `CLOCK_MONOTONIC` and `CLOCK_MONOTONIC_RAW` before and after the run:

```python
import time
raw_before = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
mono       = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
raw_after  = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
raw_mid    = (raw_before + raw_after) // 2
offset     = mono - raw_mid          # nanoseconds to add to RAW to obtain MONOTONIC
uncert     = (raw_after - raw_before) // 2   # ± half‑interval of measurement
print(f"{raw_before} {mono} {raw_after} {raw_mid} {offset} {uncert}")
```
 The resulting files (`clock_offset_pre.txt`, `clock_offset_post.txt`) are stored alongside the
 run artifacts and are used during offline validation (see `VALIDATION.md`).

*Note*: In the successful smoke‑test run the two offsets differed by **2 274 ns**. This exceeds the
 per‑measurement uncertainties (± 407 ns pre‑run, ± 305 ns post‑run) and reveals a modest **clock‑rate
 drift** of roughly 0.76 ppm over the ~3 s experiment. When merging timestamps from the BPF log,
 application log, and TCP_INFO samples, apply the appropriate offset correction to achieve precise
 alignment.

---

## 5. Instrumentation workflow (per run)
1. **Pre‑run** – record clock offset.
2. **Start** the filtered BPF probe (`bpftrace`).
3. **Wait** until the probe prints `Attaching 2 probes…` to guarantee attachment.
4. **Execute** `sender_new 3` as the `rosa` user.
5. **Collect** all CSVs (`sender_app_log.csv`, `sender_tcpinfo_log.csv`), the BPF log, and the
   probe stdout/stderr.
6. **Terminate** the probe (`kill $PID`) and record its exit status.
7. **Post‑run** – record clock offset again.

All steps are scripted in the automated smoke‑test harness; the raw artefacts are never edited.

---

## Post‑run offline analysis

The instrumentation captures raw kernel and application data.  To reason about the
semantic predicates defined for the research (D, F, C, R) an **offline analysis
step** is performed after the run:

* The script `analysis/semantic_correlation.py` parses the three logs, aligns the
  timestamps using the pre/post clock‑offset measurements, and computes the four
  predicates.
* A human‑readable evidence table (`analysis/SEMANTIC_EVIDENCE.md`) documents
  which measurements support each predicate, the computation performed, and the
  remaining uncertainty.

This analysis does not modify any raw artefacts; it only produces derived CSV
and markdown files for documentation and future classifier development.
