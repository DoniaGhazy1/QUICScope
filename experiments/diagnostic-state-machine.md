# TCP/QUIC Transport Send‑Limitation Diagnostic State Machine

## Purpose

Provide a **protocol‑independent** (Layer 1) description of *why* a transport
(TCP or QUIC) sender cannot emit new payload, and a **protocol‑specific**
(Layer 2) mapping that explains how each abstract predicate is realized and
observed in the two protocols.  The model cleanly separates **events** (single
instantaneous observations) from **states** (persistent conditions) and makes
recovery an orthogonal flag rather than part of the primary state.

---

## 1. Layer 1 – Semantic Predicates (protocol‑independent)

| Symbol | Predicate (name) | Formal definition (protocol‑agnostic) |
|--------|------------------|---------------------------------------|
| **HasTransportPendingData** | **HasTransportPendingData** | Application payload has already been submitted to the transport and remains unsent (i.e., it is queued in the transport’s send buffer but has not yet been transmitted). |
| **F** | **FlowControlAllowsNewData** | The remote endpoint has advertised enough receive credit (after any scaling or reduction) such that the sender could transmit at least one new data‑carrying packet *if* no other limitation existed. |
| **C** | **CongestionControlAllowsNewData** | The sender’s congestion‑control algorithm is in a state that **permits** the emission of additional data‑carrying packets; i.e., the algorithm does not currently forbid new transmissions. |
| **R** | **InRecovery** | The sender is currently executing a loss‑recovery procedure (fast‑recovery, selective‑ACK based recovery, timeout‑based retransmission, etc.).  This flag may be true together with any of the other predicates. |

> **Note:**  The predicates are deliberately free of any protocol‑specific
> variables such as `cwnd`, the raw TCP **Window** field, or the Linux
> `SO_SNDBUF`.  They capture the *meaning* of “there is data”, “credit
> exists”, and “congestion permits sending”, independent of any particular
> implementation.

---

## 2. Layer 1 – Events (instantaneous observations)

| Event | Meaning |
|-------|--------|
| **PKT_SENT** | A transport packet (TCP segment or QUIC packet) is transmitted onto the wire. |
| **DATA_SENT** | Unsigned application payload is transmitted as part of a packet; i.e., the sender actually emitted new data bytes. |
| **ACK_PROCESSED** | An acknowledgment is received and processed, updating flight size, remote credit, and any loss‑recovery state. |
| **LOSS_DECLARED** | The loss‑detection logic decides that one or more previously sent packets are lost (e.g., three duplicate ACKs, SACK‑based detection, or RTO). |
| **FLOW_CONTROL_UPDATE** | The remote endpoint advertises a new receive‑credit value (TCP Window, QUIC `MAX_DATA`/`MAX_STREAM_DATA`). |
 | **APP_DATA_AVAILABLE** | The application writes new payload into the sender’s transport send buffer, making **HasTransportPendingData** true. |

Events cause the Layer 1 predicates to change; the predicates in turn define the
current **state**.

---

## 3. Layer 1 – Diagnostic States (derived from predicates)

The **primary limitation state** is derived from the three *non‑recovery*
predicates `HasTransportPendingData`, `F` and `C`.  Recovery (`R`) is represented separately as an
orthogonal **RecoveryContext**.

| Primary state | Predicate condition (`HasTransportPendingData`, `F`, `C`) |
|---------------|--------------------------------------|
| **READY** | `HasTransportPendingData ∧ F ∧ C` |
| **APPLICATION_LIMITED** | `¬HasTransportPendingData ∧ F ∧ C` |
| **RECEIVER_FLOW_CONTROL_LIMITED** | `HasTransportPendingData ∧ ¬F ∧ C` |
| **CONGESTION_CONTROL_LIMITED** | `HasTransportPendingData ∧ F ∧ ¬C` |
| **MULTIPLE_LIMITERS** | `HasTransportPendingData ∧ ¬F ∧ ¬C` |
 | **INSUFFICIENT_EVIDENCE** | *One or more predicates cannot be evaluated* (e.g., missing ACKs, no endpoint instrumentation). |

**Note:** The transport’s **ground‑truth** states are the five listed above:
* **READY**
* **APPLICATION_LIMITED**
* **RECEIVER_FLOW_CONTROL_LIMITED**
* **CONGESTION_CONTROL_LIMITED**
* **MULTIPLE_LIMITERS**

The observer may additionally return **INSUFFICIENT_EVIDENCE** when the required
information is unavailable; this is **not** a transport state but an observer
classification.

**RecoveryContext** may be either `NORMAL` or `RECOVERY` and is combined with the
primary state to give a full description, e.g. `READY + RECOVERY` or
`CONGESTION_CONTROL_LIMITED + RECOVERY`.

---

## 4. Layer 2 – Protocol Realizations

Below we show how each Layer 1 predicate is realized in **TCP** and **QUIC** and
what evidence can be gathered from the **wire**, from the **endpoint**, or by
**derivation**.

### 4.1 HasUnsentData (`D`)

| Aspect | TCP | QUIC |
|--------|-----|------|
| **Realization** | Data that resides in the socket’s **send buffer** (`SO_SNDBUF`) and has not yet been transmitted.  This includes data already handed to the kernel but still awaiting transmission. | Data held in a QUIC stream’s **send buffer** (or connection‑level buffer) that has not yet been framed into a QUIC packet. |
| **Wire observability** | **None** – no TCP segment contains a flag indicating pending data. | **None** – QUIC packets contain only frames that have already been selected for transmission. |
| **Endpoint observability** | `getsockopt(SO_SNDBUF)` can report the amount of data queued for send, and many stacks expose the *unsent* byte counter via `TCP_INFO.tcpi_unacked` or custom probes. | QUIC libraries expose per‑stream pending‑byte counters (e.g., `quic_stream_pending_bytes()`).  An eBPF probe can read the internal stream buffer length. |
| **Derived / inferred?** | Must be **derived** from endpoint state; impossible to infer from the wire alone. |

### 4.2 FlowControlAllowsNewData (`F`)

#### TCP realization

The sender’s **usable send window** is based on the TCP sequence‑space variables
defined in RFC 9293:

```
SND.UNA  – oldest unacknowledged sequence number
SND.NXT  – next sequence number to be sent
SND.WND  – receiver‑advertised window (Window field of the most recent ACK, scaled by Window‑Scale)
usable_window = min(SND.WND, advertised_window) - (SND.NXT - SND.UNA)
```

If `usable_window > 0` then at least one new byte can be transmitted; otherwise
the sender is **flow‑control limited**.

#### QUIC realization

QUIC uses **cumulative flow‑control limits**:

* **Connection‑level**: `remote_max_data` – the maximum offset the peer is willing to receive.
* **Stream‑level**: `remote_max_stream_data` – the maximum offset per stream.

The sender’s **available credit** is

```
conn_credit   = remote_max_data   - conn_sent_offset
stream_credit = remote_max_stream_data - stream_sent_offset
```

Acknowledging bytes **does not** restore credit; only a new `MAX_DATA` or
`MAX_STREAM_DATA` frame from the receiver increases the limit.

#### Evidence summary

| Aspect | TCP | QUIC |
|--------|-----|------|
| **Wire (PASSIVE_ENCRYPTED_WIRE)** | TCP Window field and Window‑Scale are visible in each ACK (unencrypted). | QUIC flow‑control frames are encrypted; not visible without decryption. |
| **Wire (DECRYPTED_WIRE)** | N/A (already visible). | `MAX_DATA` / `MAX_STREAM_DATA` values are visible after keys are known. |
| **Endpoint** | Kernel maintains `snd_wnd` (effective window) and can expose it via `TCP_INFO.tcpi_rcv_space`. | QUIC stack tracks `conn->flow_control.send_window` and per‑stream `send_window`; exposed via library APIs or eBPF. |

### 4.3 CongestionControlAllowsNewData (`C`)

| Aspect | TCP | QUIC |
|--------|-----|------|
| **Realization** | The algorithm’s **congestion window** (`cwnd`) and the current **flight size** (`bytes_in_flight`).  New data may be sent when `bytes_in_flight < cwnd` (or when the algorithm’s specific probe rule permits a packet). | QUIC re‑uses the same abstract budget (`cwnd`‑like) defined by the same congestion‑control algorithm (CUBIC, BBR, …).  The rule for permitting new data is identical. |
| **Wire observability** | **Indirect** – cwnd is never transmitted.  Loss patterns (duplicate ACKs, SACK blocks, RTT spikes) can be *inferred* but do not give a definitive value. |
| **QUIC wire** | **Indirect** – same as TCP; only loss‑related ACK frames can hint at congestion state. |
| **Endpoint** | Kernel holds `snd_cwnd` (`tcp_sock->snd_cwnd`) and can expose it via `TCP_INFO.tcpi_snd_cwnd` or custom probes. |
| **QUIC endpoint** | QUIC implementations keep a congestion‑window variable; many expose it via APIs or eBPF. |

### 4.4 InRecovery (`R`)

| Aspect | TCP | QUIC |
|--------|-----|------|
| **Realization** | After loss detection (e.g., three duplicate ACKs, SACK‑based detection, or RTO) the sender sets a *recovery* flag and follows the recovery rules (fast‑retransmit, limited probing, etc.). |
| **QUIC** | RFC 9002 §7.2 defines a recovery state that is entered on the same loss‑detection triggers. |
| **Wire observability** | **Indirect** – loss events manifest as duplicate ACKs, SACK blocks, or retransmissions.  The flag itself is not transmitted. |
| **QUIC wire** | Same as TCP – only loss‑related frames are observable. |
| **Endpoint** | Kernel exposes a recovery flag (`TCP_CA_Recovery`, `tcpi_recovery_state`) via `TCP_INFO` or eBPF. |
| **QUIC endpoint** | QUIC stacks expose a recovery flag in the connection object; can be read via callbacks or probes. |

---

## 5. Evidence Taxonomy

We distinguish three **observation domains**:

1. **PASSIVE_ENCRYPTED_WIRE** – what a standard packet capture can see without any decryption keys (TCP header fields, QUIC packet headers, packet lengths, timestamps).
2. **DECRYPTED_WIRE** – what is visible after the traffic has been decrypted (e.g., with TLS keys for QUIC).
3. **ENDPOINT** – internal state exposed by the OS kernel or the QUIC library (via `getsockopt`, `TCP_INFO`, library APIs, eBPF, etc.).

| Required information | TCP PASSIVE_ENCRYPTED_WIRE | TCP ENDPOINT | QUIC PASSIVE_ENCRYPTED_WIRE | QUIC DECRYPTED_WIRE | QUIC ENDPOINT |
|----------------------|-----------------------------|--------------|-----------------------------|---------------------|----------------|
| **HasTransportPendingData** | ❌ | ✅ (TCP endpoint mechanism for HasTransportPendingData: TO BE VERIFIED) | ❌ | ❌ (still encrypted) | ✅ (stream pending bytes) |
| **F – FlowControlAllowsNewData** | ✅ (Window field, Window‑Scale) | ✅ (sender‑maintained peer receive‑window state [exact Linux exposure to be verified]) | ❌ | ✅ (`MAX_DATA`, `MAX_STREAM_DATA`) | ✅ (computed send‑window) |
| **C – CongestionControlAllowsNewData** | ❌ (cwnd not on wire) | ✅ (cwnd, flight size) | ❌ | ❌ | ✅ (cwnd‑like budget) |
| **R – InRecovery** | ❌ (only loss hints) | ✅ (recovery flag) | ❌ | ❌ | ✅ (recovery flag) |

---

## 6. State Machine (Layer 1)

```text
                +-------------------+
                |       READY       |
                 |   HasTransportPendingData ∧ F ∧ C       |
                +---------+---------+
                          |
   +----------------------+----------------------+----------------------+----------------------+
   |                      |                      |                      |
   v                      v                      v                      v
+----------------+   +----------------+   +----------------+   +-------------------+
| APP_LIMITED    |   | FC_LIMITED     |   | CC_LIMITED     |   | MULTIPLE_LIMITERS |
 | ¬HasTransportPendingData ∧ F ∧ C    |   | HasTransportPendingData ∧ ¬F ∧ C    |   | HasTransportPendingData ∧ F ∧ ¬C    |   | HasTransportPendingData ∧ ¬F ∧ ¬C        |
+----------------+   +----------------+   +----------------+   +-------------------+
          \              |              /            /
           \             |             /            /
            \            |            /            /
             \           |           /            /
              v          v          v            v
                 +--------------------------+
                 | INSUFFICIENT_EVIDENCE    |
                 +--------------------------+
```

**RecoveryContext** (`NORMAL` / `RECOVERY`) is orthogonal to the diagram and is
applied to any of the primary states, yielding composite descriptions such as
`READY + RECOVERY` or `CC_LIMITED + RECOVERY`.

---

## 7. Predicate → Evidence Mapping (Table A)

| Predicate | Meaning (Layer 1) | TCP realization (Layer 2) | QUIC realization (Layer 2) |
|-----------|-------------------|--------------------------|----------------------------|
| **HasTransportPendingData** | Transport‑pending unsent payload exists. | TCP endpoint mechanism for HasTransportPendingData: TO BE VERIFIED | Data queued in QUIC stream buffers. |
| **F** | Remote credit permits at least one new byte. | Defined using the sender's sequence/window state (SND.UNA, SND.NXT, SND.WND).  The exact reconstruction rule will be verified against RFC 9293 and Linux behavior. | `remote_max_data – conn_sent_offset` (connection) and `remote_max_stream_data – stream_sent_offset` (stream). |
| **C** | Congestion algorithm permits sending. | `bytes_in_flight < cwnd` (algorithm‑specific). | Same abstract budget as TCP, maintained by the QUIC stack. |
| **R** | Sender is in loss‑recovery. | Recovery flag (`TCP_CA_Recovery`, `tcpi_recovery_state`). | Recovery follows RFC 9002 loss‑detection and congestion‑control semantics; the QUIC connection object provides a recovery flag. |

## 8. Required Information → Observability (Table B)

See the **Evidence Taxonomy** table in Section 5.

---

## 9. Research Workflow

1. **Identify the required predicates** for a given diagnostic question (e.g., “why is the sender not sending?” → need `HasTransportPendingData`, `F`, `C`).
2. **Determine the observation domain** needed for each predicate using Table B.
3. **Collect the evidence**:
   * For TCP, try to answer everything from a passive capture (PASSIVE_ENCRYPTED_WIRE).  Anything missing requires endpoint instrumentation.
   * For QUIC, decide whether decryption keys are available.  If not, flow‑control credit (`MAX_DATA`) is only observable via the endpoint.
4. **Populate the state machine** with the evaluated predicates, remembering that `R` is orthogonal.
5. **Locate the observability gap** (e.g., `HasTransportPendingData` for QUIC without endpoint probe) and plan the minimal endpoint signal that QUICScope must request (e.g., a per‑stream pending‑byte counter).
6. **Iterate** for the remaining predicates (`F`, `C`, `R`).

---

## 10. Verification Flags (to be validated later)

| # | Assumption to verify | Why it matters |
|---|----------------------|----------------|
| **V‑1** | “Data already placed in the kernel’s send buffer counts as *pending* application data.” | Incorrect – `HasTransportPendingData` includes data already in the send buffer, but the original `A` definition excluded it. |
| **V‑2** | “A zero TCP Window field (`rwnd == 0`) is the sole condition for flow‑control limitation.” | Incorrect – usable credit depends on scaling and on the sequence‑space calculation defined above. |
| **V‑3** | “`cwnd - BytesInFlight <= 0` directly defines congestion‑control limitation.” | Incorrect – this belongs to the **TCP realization** of `C`; the semantic predicate `C` is simply “algorithm permits sending”. |
| **V‑4** | “`SO_SNDBUF` occupancy equals pending application data.” | Incorrect – `SO_SNDBUF` is the buffer *capacity*; occupancy may be zero while `HasTransportPendingData` is true because data sits in higher‑level buffers. |
| **V‑5** | “The latest raw TCP Window field equals the exact usable sender credit.” | Incorrect – the usable credit must apply the Window‑Scale factor and subtract the current flight size. |
| **V‑6** | “Limiting causes are mutually exclusive.” | Incorrect – the model includes **MULTIPLE_LIMITERS** and allows overlapping predicates. |

---

## 11. References (protocol specifications)

| RFC | Title |
|-----|----------------------------------------------|
| **RFC 9293** | *Transmission Control Protocol (TCP)* – core TCP specification. |
| **RFC 5681** | *TCP Congestion Control* – cwnd, slow start, recovery. |
| **RFC 7323** | *TCP Extensions for High Performance* – Window scaling, timestamps. |
| **RFC 2018** | *TCP Selective Acknowledgment Options* – SACK. |
| **RFC 6298** | *Computing TCP Retransmission Timer* – RTO. |
| **RFC 9000** | *QUIC Transport Protocol* – flow‑control signalling (MAX_DATA, MAX_STREAM_DATA). |
| **RFC 9002** | *QUIC Loss Detection and Congestion Control* – recovery, cwnd‑like budget. |
| **RFC 9221** | *QUIC Datagram Frames* – optional datagram flow‑control. |

---

### End of Document

*No experiments have been executed and no system‑changing commands have been run.*
