# TCP-FC-001 – Controlled TCP Receiver Flow‑Control Limitation (Plan)

**Purpose** – Design an experiment that isolates the *receiver‑flow‑control*
predicate `F = FlowControlAllowsNewData` (as defined verbatim in
`docs/diagnostic-state-machine.md`).  The target controlled state is

```
D = true      (sender has pending data at the transport)
F = false     (receiver does **not** permit new data)
C = true      (congestion control does not limit sending)
```

This corresponds to the semantic state **RECEIVER_FLOW_CONTROL_LIMITED**.
The experiment is purely observational: we ask *"What evidence does TCP
expose to a passive observer when receiver flow control prevents the sender
from transmitting additional new data?"*  No throughput benchmarks, no kernel
parameter changes, and no off‑load disabling are performed.

---

## 1. Research Question

*What evidence does a passive observer see on the wire when the receiver’s
advertised credit becomes insufficient for the sender to emit new data?*

The predicate `FlowControlAllowsNewData` is defined in
`docs/diagnostic-state-machine.md` as:

> **FlowControlAllowsNewData** – The receiver’s advertised receive credit,
> after applying any negotiated window‑scale, is sufficient for the sender
> to transmit at least one new data segment given the sender’s current
> sequence‑space state.

The experiment must demonstrate whether a passive observer can infer the
truth value of this predicate.

---

## 2. Important TCP Distinction

derives a *usable‑credit* value from the observable fields; it does **not** compare it against the MSS.
A **raw Window field** (`win` in the TCP header) is *visible* on the wire and
belongs to the **WIRE_DIRECT** evidence class.  After applying the negotiated
scale factor it yields the **scaled advertised receive window** – a **WIRE_DERIVED**
quantity.

**Semantic `F`** is *not* simply “`win` ≠ 0”.  `F` depends on the *usable* receive
credit, which is the intersection of the advertised window and the sender’s
current sequence‑space state (`observed_snd_nxt` and `snd_una`).  The plan therefore
derives a *usable‑credit* value from the observable fields; it does **not** compare it against the MSS.

---

## 3. Controlled Workload Design

### General Setup

* **Port** – Use a dedicated TCP port `5203` for the experiment.
* **Hosts** – VM1 (`192.168.88.20`) runs the **sender** *and* the passive
  observer.  VM2 (`192.168.88.21`) runs the **receiver**.
* **No off‑load or sysctl changes** – The experiment relies on default kernel
  behaviour; only socket‑level options may be set (e.g. `SO_RCVBUF`).

### Sender (back‑logged data source)

1. **Connect** to the receiver on port 5203.
2. **Enter a tight loop** that repeatedly calls `send()` with a large buffer
   (e.g. 64 KB) *without* any artificial sleep.
3. The loop continues for the entire duration of the experiment, thereby
   keeping the application’s transmit queue full.  If `send()` returns fewer
   bytes than requested (or, for a non‑blocking socket, raises `EAGAIN`/`EWOULDBLOCK`), the sender logs the event as *send‑blocked* – this is **application‑level evidence** that the transport is not accepting all offered data at that moment.  It supports the back‑log argument but **is not a direct proof** of the semantic predicate `D = true`.
4. No explicit `shutdown()` until the experiment concludes.

### Receiver (induced flow‑control pressure)

1. **Accept** the connection on port 5203.
2. **Phase B – Normal consumption**: read from the socket in a loop (e.g.
   `recv(64 KB)`) until at least **8 MiB** of data have been received
   (`cumulative_bytes >= 8 * 1024 * 1024`).  This deterministic byte‑count
   threshold ensures the receiver will enter the pause independent of link
   speed, while still providing enough traffic to keep the receive buffer
   filled and the advertised window near its maximum.
3. **Phase C – Intentional pause**: stop calling `recv()` and **sleep** for a
   controlled interval (e.g. 200 ms).  The interval must be long enough for the
   kernel’s receive buffer to fill and for the advertised window to shrink
   substantially (potentially to zero).  The exact duration can be tuned on the
   first trial; a safe baseline is **≥ 150 ms** on a typical Linux default
   receive‑buffer size (≈ 212 KB).
4. **Phase E – Resume**: after the pause, resume reading until the connection
   is closed.
5. Throughout, log timestamps for *pause‑start*, *pause‑end*, and the total
   bytes read.

**NOTE** – The receiver’s pause is *application‑level*; we do *not* modify the
kernel `net.ipv4.tcp_rmem` values.  If the default receive buffer is too large
to be exhausted within a reasonable pause, the receiver may optionally set a
smaller size via `setsockopt(SO_RCVBUF)` (e.g. 256 KB) – this is still a
purely endpoint‑local action.

---

## 4. Expected Phases (chronological)

| Phase | Description |
|------|-------------|
| **A** | TCP three‑way handshake (connection establishment). |
| **B** | Receiver reads normally; advertised window stays high; sender
  continuously injects data (back‑logged). |
| **C** | Receiver stops reading (pause). |
 | **D** | Advertised receive credit **shrinks**; may reach zero or any value that makes the usable credit reach zero. |
 | **E** | Candidate constrained interval – passive analysis determines whether receiver usable credit reaches zero and whether new‑data sequence progress stops. The advertised window may shrink but is not assumed to reach zero. |
 | **F** | Receiver resumes reading; advertised window expands; sender may resume transmitting new data, and new‑data sequence progress continues. |

The timeline is captured by both endpoints (see § 5) and by the passive
observer.

---

## 5. Controlled Timelines (application logs)

Both programs will write a CSV‑style log (`timestamp_ns,event,detail`).  Example
fields are shown; the exact format can be refined later.

### Sender timeline (`sender_timeline.log`)

| Event | Meaning |
|------|---------|
| `conn_established` | TCP handshake completed. |
| `send_start` | Beginning of the back‑logged sending loop. |
| `send_progress` | Number of bytes accepted by each `send()` call. |
| `send_blocked` | `send()` returned `EAGAIN` or partial write – indicates
  back‑log (`D = true`). |
| `send_end` | End of experiment (socket close). |

### Receiver timeline (`receiver_timeline.log`)

| Event | Meaning |
|------|---------|
| `conn_accepted` | TCP handshake completed on the receiver side. |
| `read_normal_start` | Beginning of normal consumption phase. |
| `read_normal_progress` | Bytes read during normal phase. |
| `recv_pause_start` | Receiver intentionally stops reading. |
| `recv_pause_end` | Receiver resumes reading. |
| `read_resume_progress` | Bytes read after resume. |
| `close` | Socket close. |

All timestamps use `time.time_ns()` (epoch nanoseconds) to align with the
pcap timestamps, which are also epoch‑based.

---

## 6. Passive Capture

Capture is performed **only on VM 1** (the sender side) using `tcpdump` as in
`TCP-APP-001` runs.

```bash
tcpdump -i ens4 -w tcp_capture.pcap -s 256 -U "tcp and port 5203" \
    -Z $(id -un) &
```

* **snaplen** – 256 bytes (captures full TCP header and first part of payload).
* **-U** – unbuffered, so the file can be read while the capture is running.
* **PID tracking** – store the PID, send SIGINT after the experiment, then
  verify the pcap integrity (no truncation, correct number of packets).
* Re‑use the *capture‑lifecycle* scripts from `run‑004` (environment.txt,
  capture_stats.txt, etc.).

---

## 7. Passive Flow‑Control Analysis (offline)

The analysis will be performed on the resulting `tcp_capture.pcap` and the
application timelines.  The steps are:

176 | *Parse the SYN and SYN‑ACK* to obtain the `Window Scale` option (`wscale`) as
177 | defined in **RFC 7323 § 2.3**.  The Window Scale option is advertised **by each
178 | endpoint in its own SYN (client) or SYN‑ACK (server)**.  An endpoint must apply
179 | the *scale factor it advertised* to every `Window` field it later sends in
180 | segments (including ACKs).  Consequently:
181 |
182 | - For VM2 → VM1 (server → client) ACK/window advertisements, the raw `win`
183 |   field must be left‑shifted by the **scale factor advertised by VM2 in its
184 |   SYN‑ACK** (`B`).
185 |
186 | - For VM1 → VM2 (client → server) ACK/window advertisements, the raw `win`
187 |   field must be left‑shifted by the **scale factor advertised by VM1 in its
188 |   SYN** (`A`).
189 |
190 | The SYN and SYN‑ACK themselves contain an unscaled `Window` field; scaling
191 | applies only to subsequent Window fields.
<!-- Removed outdated scaling description; the correct direction is now documented above. -->

### B. Advertised receive window (WIRE_DIRECT & WIRE_DERIVED)

*For packets from **receiver → sender** (`192.168.88.21:5203 → 192.168.88.20`):*
  - Extract the raw `win` field → **WIRE_DIRECT**.
  - Compute `scaled_win = win * 2**wscale` → **WIRE_DERIVED**.  This value
    corresponds to the *send‑window size* (`snd_wnd`) maintained by the sender,
    per **RFC 9293 § 3.9.2**.

### C. Sender‑side window state reconstruction

From the **sender → receiver** direction (`192.168.88.20:5203 → 192.168.88.21`),
reconstruct the variables defined in **RFC 9293 § 3.9**:

* **`observed_snd_nxt`** (also called *sender_sequence_high_water*) – the highest
  *new‑data* sequence number observed in the trace.  For each data segment the
  candidate value is `candidate_nxt = SEQ + payload_len` (including 1 B for SYN
  and FIN).  If `candidate_nxt > observed_snd_nxt` then set `observed_snd_nxt =
  candidate_nxt`.  Retransmissions, zero‑window probes, and out‑of‑order
  segments that do not increase `candidate_nxt` are ignored.

* **`snd_una`** – the oldest un‑acknowledged sequence number (left edge of the
  send window).  Upon receiving an ACK segment, if `SEG.ACK > snd_una` then
  set `snd_una = SEG.ACK`.  This follows the ACK‑advancement rule in RFC 9293
  § 3.9.2.

* **Window update (`snd_wnd`, `snd_wl1`, `snd_wl2`)** – the advertised receive‑window
  size and its update markers.  The sender updates the window only when the ACK
  is acceptable and the segment is newer than the last window update, as defined
  in RFC 9293 § 3.9.2:

  - The ACK is acceptable iff `snd_una <= SEG.ACK <= observed_snd_nxt`.
  - The *window‑update condition* is `(snd_wl1 < SEG.SEQ) or (snd_wl1 == SEG.SEQ`
    `and snd_wl2 <= SEG.ACK)`.

  If both hold, set:

  ```
  snd_wnd = scaled_win
  snd_wl1 = SEG.SEQ
  snd_wl2 = SEG.ACK
  ```

* **Initialization at connection establishment** – After processing the SYN/
  SYN‑ACK exchange, the following initial values apply (per RFC 9293 § 3.9):
  - `snd_una` = `ISS` + 1 (the SYN consumes one sequence number).
  - `observed_snd_nxt` = `ISS` + 1 (plus any data carried in the SYN, which is
    typically none).
  - `snd_wnd` = scaled window advertised in the SYN‑ACK (the Window field
    multiplied by the negotiated shift factor).
  - `snd_wl1` and `snd_wl2` are set to the sequence and acknowledgment numbers
    of the SYN segment.

* **`snd_wnd`** – the advertised receive‑window size of the remote side (the
  scaled `win` field).  This is the **WIRE_DERIVED** quantity.

With these variables the *right edge* of the sender’s send window is:

```text
right_edge = snd_una + snd_wnd   // bytes, modulo 2^32 (RFC 9293 § 2.3)
```

The **receiver‑flow‑control usable credit** that determines `F` is then:

```text
usable_credit = right_edge - observed_snd_nxt
```

Interpretation:
* `usable_credit > 0` – receiver still advertises credit; new data may be sent
  (`F = true`).
* `usable_credit == 0` – advertised credit exactly matches the highest transmitted
  byte; **no additional new sequence space is permitted** (`F = false`).
* `usable_credit < 0` – indicates a protocol anomaly (e.g., loss or reordering);
  such intervals are treated as **ambiguous**.

This definition purposefully excludes any congestion‑control term (`snd_cwnd`)
and does **not** compare against the MSS; any positive credit, even less than a
full‑size segment, means `F` remains true.

#### Zero‑window special case

When the scaled advertised window (`scaled_win`) is 0, the sender's right edge
collapses to `snd_una`.  Consequently the usable credit becomes
`usable_credit = snd_una - observed_snd_nxt`.  If `observed_snd_nxt` equals
`snd_una`, the usable credit is exactly 0, representing a flow‑control limit
where the receiver has closed its receive window.  TCP zero‑window probes –
small (often 1 B) segments sent with `SEQ == observed_snd_nxt` – are not
considered new‑data progress and therefore do **not** advance
`observed_snd_nxt`.  This behaviour follows RFC 9293 § 3.9.2, which specifies
that such probes are ignored for the purpose of advancing the send‑window.

### D. Flow‑control transition detection

1. Locate `recv_pause_start` / `recv_pause_end` timestamps from the receiver
   timeline.
2. Verify that during the pause the derived `snd_wnd` (i.e., `scaled_win`) shrinks
   such that `usable_credit` reaches **zero**.
3. Confirm that `observed_snd_nxt` ceases to advance (no new‑data sequence numbers are
   observed) for the entire interval where `usable_credit == 0`.
4. After `recv_pause_end`, check that `snd_wnd` expands, `usable_credit` becomes
   positive, and `observed_snd_nxt` resumes advancing, indicating the flow‑control
   limitation has been lifted.

---
### E. Packet classification (passive trace analysis)

For the passive observer to correctly interpret the *new‑data* progress condition, packets must be classified as follows:

* **Sender → receiver data packets**
  * *New data* – a segment whose sequence number (`SEQ`) is greater than any previously observed `observed_snd_nxt`.  This advances the high‑water mark.
  * *Retransmission* – a segment with `SEQ` within the range `[previous snd_una, previous observed_snd_nxt)`.  The observer should treat these as not contributing to new‑data progress.
  * *Zero‑window probe* – a segment (often 1 byte) sent by the sender when the advertised window is zero.  It carries data but does **not** indicate new application data; its purpose is to probe for credit.
* **Receiver → sender ACK/window update**
  * Segments with no payload (`len(payload) == 0`) that contain an updated `ACK` and/or `WIN` field are treated as pure window management messages.

During the analysis, only *new‑data* packets are used to advance `observed_snd_nxt`.  All other packet types (retransmissions, probes, pure ACKs) are ignored for the purpose of detecting the cessation of new‑data sequence‑space advancement.

---

## 8. Ground Truth vs Observer

| Layer | Information |
|-------|--------------|
| **CONTROLLED_GROUND_TRUTH** | Receiver deliberately pauses `recv()`.  Sender continuously calls `send()` (back‑logged). |
| **PASSIVE OBSERVATION** | Packet headers (`seq`, `ack`, raw `win`), timestamps, and derived quantities (scaled window, usable credit). |
| **DERIVED** | Scaled advertised window (`snd_wnd`), sender high‑water mark (`observed_snd_nxt`), cumulative ACK (`snd_una`), usable credit (`right_edge - observed_snd_nxt`) – all reconstructed from the passive trace as described in § 7. |
| **OBSERVER DIAGNOSIS** | *Receiver‑flow‑control‑limited* – i.e. `F` inferred to be false because usable credit reaches **zero** during the receiver pause (not merely `< MSS`). |

The plan **does not** declare `F = false` solely on the basis of the receiver
application’s pause; the inference must be supported by the derived usable‑
credit calculation.

---

## 9. C and D Confounders

* **Sender back‑log (`D = true`)** – Verified by sender logs showing *send‑blocked* events (or, for a blocking socket, consistently long `send()` call durations) or that the amount of data accepted per `send()` call is consistently less than the request size.  These observations provide **application‑level evidence** of a back‑logged sender but are not a direct proof of the semantic predicate `D = true`.
* **Congestion (`C`)** – The passive trace will be examined for loss,
  retransmissions, duplicate ACKs, or explicit ECN signals.  The absence of
  such events *does not* automatically prove `C = true`; the result will be
  recorded as **unknown** unless a clean trace confirms no congestion.
* **Network path** – Use the same LAN configuration as previous experiments to
  avoid induced loss or bandwidth limits.

---

## 10. Success / Ambiguity / Failure Criteria

| Outcome | Evidence required |
|---------|-------------------|
| **VALID FLOW‑CONTROL‑LIMITED OBSERVATION** | (1) Receiver pause timestamps present. (2) Scaled window shrinks during the pause. (3) Derived usable credit reaches **zero** (or ≤ 0) for a non‑zero interval. (4) Sender’s `observed_snd_nxt` (new‑data sequence number) stops advancing while usable credit is zero. (5) After the pause, the scaled window expands and `observed_snd_nxt` resumes advancing, indicating new data transmission. |
| **AMBIGUOUS** | Any of the above conditions missing or contradictory – e.g. window shrinks but usable credit never reaches zero, sender continues advancing `observed_snd_nxt` despite zero credit, or loss/retransmission events mask the flow‑control effect. |
| **FAILED TO INDUCE FLOW‑CONTROL LIMITATION** | Receiver pause does not cause a
  noticeable reduction in advertised window, or sender never stalls, or the
  experiment terminates before the pause interval elapses. |

The final report will categorise the run accordingly.

---

## 11. Expected Artifacts

```
TCP-FC-001/
  PLAN.md                     ← this document
  sender.py                   ← to be implemented later
  receiver.py                 ← to be implemented later
  run-001/
    environment.txt           ← environment snapshot (uname, sysctl, etc.)
    sender.log                ← stdout/stderr of sender process
    sender_timeline.log       ← CSV timeline described in § 5
    receiver.log              ← stdout/stderr of receiver process
    receiver_timeline.log     ← CSV timeline described in § 5
    tcp_capture.pcap          ← raw passive capture (port 5203)
    capture_stats.txt         ← tcpdump exit status, packet counts
    sender_exit.txt           ← process exit code
```

Only `PLAN.md` is required at this stage.

---

## 12. Connection to QUICSCOPE

TCP exposes the receiver’s flow‑control state directly in the TCP header
(`Window` and `Window‑Scale`).  A passive observer can therefore *derive* the
usable receive credit and, with the sender’s sequence information, infer whether
the sender is flow‑control limited.

By contrast, QUIC carries analogous flow‑control limits in encrypted frames
(`MAX_DATA`, `MAX_STREAM_DATA`).  Those values are not observable to a generic
passive wire‑tap.  Demonstrating that TCP’s flow‑control limitation is
passively inferable establishes the baseline for a later comparison with QUIC,
where the observer must rely on *absence* of such visible signals.

---

**End of Plan**
