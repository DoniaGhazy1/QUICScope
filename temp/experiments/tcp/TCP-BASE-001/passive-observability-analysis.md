# Passive Observability Analysis for TCP-BASE-001 (run‑002)

**Scope** – This document presents *the passive TCP evidence examined for the
QUICScope semantic predicates in TCP-BASE-001*.  It does **not** claim to
enumerate every possible TCP passive signal; it only records the signals that
are present in the captured trace of **run‑002**.

**Evidence source** – All observations come from the pcap file:

```
/home/rosa/experiments/tcp/TCP-BASE-001/run-002/tcp_capture.pcap
```

The bulk‑data flow studied is:

```
192.168.88.20:54030 <-> 192.168.88.21:5201
```

---
## Step 1 – Representative packets (raw header evidence)

The following four packets are the first occurrences of each logical class
required for the analysis.

### A – SYN (client → server)

```text
2026-10-07 16:46:59.198082 IP (tos 0x0, ttl 64, id 61321, offset 0, flags [DF], proto TCP (6), length 60)
    192.168.88.20.54030 > 192.168.88.21.5201: Flags [S], cksum 0x31a9 (incorrect -> 0x1e07), seq 247160118, win 64240, options [mss 1460,sackOK,TS val 2913336470 ecr 0,nop,wscale 7], length 0
```

### B – SYN‑ACK (server → client)

```text
2026-10-07 16:46:59.198165 IP (tos 0x0, ttl 64, id 0, offset 0, flags [DF], proto TCP (6), length 60)
    192.168.88.21.5201 > 192.168.88.20.54030: Flags [S.], cksum 0x1975 (correct), seq 143155987, ack 247160119, win 65160, options [mss 1460,sackOK,TS val 3456812866 ecr 2913336470,nop,wscale 7], length 0
```

### C – Data (client → server, first PSH segment)

```text
2026-10-07 16:46:59.198197 IP (tos 0x0, ttl 64, id 61323, offset 0, flags [DF], proto TCP (6), length 89)
    192.168.88.20.54030 > 192.168.88.21.5201: Flags [P.], cksum 0x31c6 (incorrect -> 0xdf7b), seq 247160119:247160156, ack 143155988, win 502, options [nop,nop,TS val 2913336470 ecr 3456812866], length 37
```

### D – ACK (server → client, first pure ACK)

```text
2026-10-07 16:46:59.198395 IP (tos 0x0, ttl 64, id 8424, offset 0, flags [DF], proto TCP (6), length 52)
    192.168.88.21.5201 > 192.168.88.20.54030: Flags [.], cksum 0x44a8 (correct), seq 143155988, ack 247160156, win 509, options [nop,nop,TS val 3456812866 ecr 2913336470], length 0
```

For each packet the fields listed below are directly visible in the capture.

| Packet | Field | Example value | Evidence level |
|--------|-------|---------------|----------------|
| A (SYN) | src IP / dst IP | 192.168.88.20 / 192.168.88.21 | **WIRE_DIRECT** |
| A | src port / dst port | 54030 / 5201 | **WIRE_DIRECT** |
| A | TCP flags | SYN | **WIRE_DIRECT** |
| A | Sequence number | 247160118 | **WIRE_DIRECT** |
| A | Window (raw) | 64240 | **WIRE_DIRECT** |
| A | Options (MSS, SACK‑OK, TS, wscale) | mss 1460, sackOK, TS(val 2913336470,ecr 0), wscale 7 | **WIRE_DIRECT** |
| B (SYN‑ACK) | src/dst IP & ports | 192.168.88.21 / 192.168.88.20, ports 5201 / 54030 | **WIRE_DIRECT** |
| B | TCP flags | SYN + ACK | **WIRE_DIRECT** |
| B | Sequence number | 143155987 | **WIRE_DIRECT** |
| B | Acknowledgment number | 247160119 | **WIRE_DIRECT** |
| B | Window (raw) | 65160 | **WIRE_DIRECT** |
| B | Options (MSS, SACK‑OK, TS, wscale) | same as A | **WIRE_DIRECT** |
| C (data) | TCP flags | PSH + ACK | **WIRE_DIRECT** |
| C | Sequence range | 247160119‑247160156 (37 bytes) | **WIRE_DIRECT** |
| C | Ack number | 143155988 | **WIRE_DIRECT** |
| C | Window (raw) | 502 | **WIRE_DIRECT** |
| C | Options (TS) | TS(val 2913336470, ecr 3456812866) | **WIRE_DIRECT** |
| C | Payload length | 37 | **WIRE_DERIVED** (IP length – headers) |
| D (ACK) | TCP flags | ACK | **WIRE_DIRECT** |
| D | Sequence number | 143155988 | **WIRE_DIRECT** |
| D | Ack number | 247160156 | **WIRE_DIRECT** |
| D | Window (raw) | 509 | **WIRE_DIRECT** |
| D | Options (TS) | TS(val 3456812866, ecr 2913336470) | **WIRE_DIRECT** |

No ECN‑related flags (`ECE`, `CWR`) or IP ECN bits appear in any of the packets.
The fields themselves are **WIRE_DIRECT** but they are *not asserted/observed*
in this baseline trace.

---
## Step 2 – Evidence classification summary

The table above already annotates each observable field with one of the
evidence levels defined for this document:

- **WIRE_DIRECT** – field/value directly observable in captured headers.
- **WIRE_DERIVED** – deterministically computed from directly observed wire
  fields (e.g., payload length, scaled window size).
- **WIRE_INFERRED** – heuristic or model‑based inference about endpoint
  state derived from packet behavior (not used for the concrete examples
  below).
- **ENDPOINT** – internal endpoint state that would be required as ground
  truth but is not visible on the wire.

---
## Step 3 – TCP flow‑control evidence

*Window‑scaling negotiation* – Both the SYN (packet A) and the SYN‑ACK (packet B)
contain the option `wscale 7`.  Therefore each side advertises a scaling
factor of **7**, i.e. a multiplier of `2⁷ = 128`.

*Receiver‑advertised window* – The first pure ACK from the server (packet D)
advertises a raw window field of **509**.  Applying the negotiated scale‑factor
gives a **scaled advertised window** of:

```
509 << 7 = 509 × 128 = 65 152 bytes
```

The raw window (`509`) is **WIRE_DIRECT**; the scaled value is **WIRE_DERIVED**
because it requires applying the negotiated scale factor.

---
## Step 4 – Outstanding‑data estimate (WIRE_DERIVED)

The passive observer can compute a *sequence‑space high‑water estimate* of the
number of bytes the sender has transmitted but the receiver has not yet
cumulatively ACKed.  This estimate is **wire‑derived** and must be performed
**per‑flow and per‑direction** with the following considerations:

1. **Sequence‑space consumption** – A SYN consumes one sequence number; a FIN
   consumes one sequence number.  An RST **does not** consume sequence space
   merely because the RST flag is set (RFC 793 states that an RST without data
   does not advance the sequence number).  In our trace the connection ends
   with an RST, so the RST does not affect the outstanding‑data calculation.
2. **Retransmissions** – Duplicate copies of a segment reuse the original
   sequence numbers.  The observer must track the *highest* sequence number
   transmitted (high‑water mark) rather than counting packets.
3. **Sequence tracking** – Tracking must always be per‑flow (source‑IP/port ↔
   dest‑IP/port) and per‑direction (sender → receiver vs. receiver → sender).
4. **Gaps, reordering, and SACK** – Gaps in sequence numbers, out‑of‑order
   delivery, retransmissions, and SACK blocks can make a simple
   `highest‑seq – cumulative‑ACK` calculation differ from the amount of unique
   contiguous data that is truly outstanding.  Consequently the document treats
   the calculation as a *sequence‑space high‑water estimate*, not an exact
   sender `bytes_in_flight`.
5. **Cumulative ACK semantics** – The ACK number denotes the next byte the
   receiver expects, i.e. `ACK = last_byte_received + 1`.  Using the latest
   cumulative ACK together with the sender’s high‑water sequence yields the
   estimate.
6. **32‑bit wrap‑around** – The calculation must correctly handle the case where
   the 32‑bit sequence number rolls over; this is normally done by using
   unsigned‑integer arithmetic modulo 2³².
7. **Capture completeness** – The estimate is only as accurate as the capture;
   missing packets (e.g., due to loss on the capture interface) will cause the
   observer to under‑estimate the true outstanding bytes.

Applying the formula to the first data segment (packet C) and the following
ACK (packet D):

- After the SYN, the sender’s next sequence number is `247160118 + 1 = 247160119`.
- The PSH segment advances it to `247160156` (because the segment spans 37
  bytes).
- The receiver’s ACK in packet D is `247160156`.
- `outstanding = 247160156 – 247160156 = 0` bytes now outstanding.

Later in the trace the same calculation can be repeated with the highest
sequence numbers observed up to any point to obtain a running estimate of the
outstanding data.

---
## Step 5 – What the wire does **not** directly reveal

| Semantic item | Evidence level | Comment |
|---------------|----------------|---------|
| **HasTransportPendingData (D)** – application payload has already been submitted to the transport and remains unsent / queued at the transport send boundary. It does **not** refer to data still owned or buffered by the application before submission. | **WIRE_INFERRED** (potential) | The exact D predicate is not encoded in TCP headers. Passive systems may attempt to infer a non‑backlogged / application‑limited state from packet pacing or lack of new data, but such inference is heuristic and not a direct observation. |
| Sender congestion window `cwnd` | **WIRE_INFERRED** (potential) | Not present in the wire; inference would rely on observed flight size, loss events, and RTT trends. |
| Congestion‑control permission `C` (whether the sender is allowed to send) | **WIRE_INFERRED** (potential) | Derivable only through a model of the sender’s algorithm combined with observed ACK/RTT behavior. |
| Recovery state (fast‑recovery, loss‑recovery, etc.) | **WIRE_INFERRED** (potential) | Can sometimes be hinted at by patterns such as duplicate ACKs or selective ACK blocks, but the state is internal to the endpoint. |
| Exact `bytes_in_flight` as maintained by the kernel | **ENDPOINT** | The passive observer can **derive** an estimate of outstanding bytes (see Step 4) but this should not be equated with the kernel’s internal `bytes_in_flight` accounting. |

The table makes it clear that the exact endpoint state is **not directly**
encoded in TCP headers; any higher‑level inference would be heuristic and is
outside the scope of this document.

---
## Step 6 – Concise observability table

| Semantic evidence | Source (packet / field) | Evidence level | Limitation |
|-------------------|-------------------------|----------------|------------|
| Source IP address | A‑D (`src`) | **WIRE_DIRECT** | – |
| Destination IP address | A‑D (`dst`) | **WIRE_DIRECT** | – |
| Source TCP port | A‑D (`src port`) | **WIRE_DIRECT** | – |
| Destination TCP port | A‑D (`dst port`) | **WIRE_DIRECT** | – |
| TCP flags (S, S., P., .) | A‑D (`flags`) | **WIRE_DIRECT** | – |
| Sequence numbers (incl. range) | A, B, C, D (`seq`) | **WIRE_DIRECT** | – |
| Acknowledgment numbers | B, C, D (`ack`) | **WIRE_DIRECT** | – |
| Raw receive‑window (`win`) | A, B, C, D | **WIRE_DIRECT** | Only 16‑bit raw value; scaling required for true size |
| Scaled advertised window (receiver) | D + negotiated wscale | **WIRE_DERIVED** | Requires correct wscale (7) from handshake |
| TCP options (MSS, SACK‑OK, Timestamp, Window‑scale) | A, B | **WIRE_DIRECT** | – |
| Payload length | C (`length 37`) | **WIRE_DERIVED** (IP length – headers) | Only for packets that carry data |
| ECN flags (ECE, CWR) & IP ECN bits | – (absent) | **WIRE_DIRECT** (field exists) but *not asserted/observed* in this run | No occurrence in the trace |
| Outstanding‑data estimate (bytes sent but not ACKed) | Derived from highest `seq` and latest cumulative `ack` (e.g., packets C & D) | **WIRE_DERIVED** | Requires per‑direction tracking, handling of SYN/FIN consumption, retransmissions, duplicate ACKs, gaps/reordering, SACK, wrap‑around, and capture completeness |
| HasTransportPendingData (D) | – | **WIRE_INFERRED** (potential) | Not directly observable; inference would be heuristic |
| Sender congestion window `cwnd` | – | **WIRE_INFERRED** (potential) | Not directly observable; inference would be heuristic |
| Congestion‑control permission `C` | – | **WIRE_INFERRED** (potential) | Not directly observable; inference would be heuristic |
| Recovery state | – | **WIRE_INFERRED** (potential) | Not directly observable; inference would be heuristic |
| Kernel `bytes_in_flight` | – | **ENDPOINT** | Passive observer’s outstanding‑data estimate should not be equated with this internal counter |

*End of analysis.*
