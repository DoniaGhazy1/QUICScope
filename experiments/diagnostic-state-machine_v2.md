# diagnostic-state-machine_v2.md

## Overview

This document defines a **two‑layer** diagnostic model for understanding why a
transport (TCP or QUIC) sender cannot transmit new data.  

* **Layer 1 – Protocol‑independent semantics** – pure logical predicates that
  describe the *observable* state of a connection without referring to any
  concrete protocol fields.
* **Layer 2 – Protocol realization** – for each Layer‑1 predicate we state how
  it is manifested in TCP and in QUIC, and what evidence (wire or endpoint)
  can be used to determine the predicate’s truth value.

The model explicitly separates **events** (instantaneous occurrences) from
**states** (conditions that persist over time).  It also allows multiple
limiting factors to be present simultaneously and defines a special
`INSUFFICIENT_EVIDENCE` state for cases where the available observations are
inadequate.

---

## 1. Layer 1 – Protocol‑Independent Diagnostic Semantics

### 1.1 Semantic Predicates

| Symbol | Predicate (name) | Formal definition (protocol‑agnostic) |
|--------|------------------|---------------------------------------|
| **A** | **HasPendingApplicationData** | The application (or higher‑level protocol) has generated at least one byte of payload that has **not yet been handed to the transport** for transmission.  This is *pre‑send‑queue* data, not data already in the socket’s send buffer. |
| **F** | **FlowControlAllowsNewData** | The remote endpoint has advertised sufficient receive credit **after all protocol‑level scaling and reductions** so that the sender could issue at least one new data‑carrying packet *if* no other limitation existed. |
| **C** | **CongestionControlAllowsNewData** | The sender’s congestion‑control algorithm (whichever algorithm is in use) is in a state that *permits* the emission of additional data‑carrying packets, i.e., the algorithm does *not* currently forbid new transmissions. |
| **R** | **InRecovery** | The sender is currently executing a loss‑recovery procedure (fast‑recovery, selective‑ACK based recovery, timeout‑based retransmission, etc.).  This flag may be true together with any of the other predicates. |

> **Note:**  The predicates deliberately avoid any reference to TCP‑specific
> variables such as `cwnd`, the raw TCP **Window** field, or the Linux
> `SO_SNDBUF`.  They capture the *meaning* of “there is credit”, “congestion
> allows sending”, etc., independent of the underlying protocol.

### 1.2 Diagnostic **States** (derived from predicates)

| State | Entry condition (predicate logic) | Exit condition | Remarks |
|-------|-----------------------------------|----------------|---------|
| **READY** | `A ∧ F ∧ C ∧ ¬R` | Any predicate becomes false (e.g., `¬A`, `¬F`, `¬C` or `R`) | Normal operation – the sender can emit new data immediately. |
| **APPLICATION_LIMITED** | `¬A ∧ F ∧ C ∧ ¬R` | `A` becomes true or another predicate (`¬F` or `¬C`) becomes false | No application data is waiting; other resources are available. |
| **RECEIVER_FLOW_CONTROL_LIMITED** | `A ∧ ¬F ∧ C ∧ ¬R` | `F` becomes true (credit appears) or `A` becomes false or `¬C` | Remote receive credit is insufficient for at least one new packet. |
| **CONGESTION_CONTROL_LIMITED** | `A ∧ F ∧ ¬C ∧ ¬R` | `C` becomes true (congestion window expands / flight size shrinks) or `A` becomes false or `¬F` | Sender’s congestion algorithm is currently gating transmission. |
| **MULTIPLE_LIMITERS** | `A ∧ (¬F ∨ ¬C) ∧ (¬F ∧ ¬C) ∧ ¬R` | Any of the limiting predicates (`¬F`/`¬C`) becomes true (i.e., only one limiter remains) | Both flow‑control and congestion‑control are simultaneously blocking new data. |
| **INSUFFICIENT_EVIDENCE** | *Cannot determine the truth value of one or more predicates because the observer lacks the required information* | When sufficient evidence becomes available | Used when the observer (e.g., a passive packet trace) cannot reconstruct a predicate. |
| **(Recovery context)** | `R` may be true in **any** of the above states; it is *not* a mutually exclusive state but an orthogonal flag. | `¬R` when the recovery procedure ends. | Allows diagnosis such as “READY + InRecovery” or “CONGESTION_CONTROL_LIMITED + InRecovery”. |

### 1.3 Events (instantaneous observations)

| Event | Description |
|-------|-------------|
| **PKT_SENT** | A data‑carrying packet (or a control packet that consumes flow‑control credit) is transmitted onto the wire. |
| **ACK_PROCESSED** | An acknowledgment is received and processed by the sender, updating any required state (e.g., flight size, remote credit). |
| **LOSS_DECLARED** | The sender’s loss‑detection algorithm decides that one or more previously sent packets are lost (e.g., after three duplicate ACKs or timeout). |
| **FLOW_CONTROL_UPDATE** | The remote endpoint advertises a new receive window (or its QUIC equivalent) that changes the amount of credit available to the sender. |
| **APP_DATA_AVAILABLE** | The application writes new payload to the transport’s *pre‑send* buffer, making `A` true. |

Events trigger changes in the Layer‑1 predicates; states are derived from the
current predicate values.

---

## 2. Layer 2 – Protocol Realization

For each Layer‑1 predicate we describe how it is **realized** in TCP and in
QUIC, and we list what can be observed **on the wire**, **from the endpoint**,
or **derived** from the wire.

### 2.1 HasPendingApplicationData (A)

| Aspect | TCP | QUIC |
|--------|-----|------|
| **Realization** | The socket’s *pre‑send* queue contains bytes that have not yet been placed into the kernel’s transmit queue.  This is distinct from the data already staged in the kernel’s send buffer (`SO_SNDBUF`). | The QUIC implementation’s stream buffers hold data that have not yet been framed into a QUIC packet. |
| **Wire observability** | **None** – no packet contains a flag indicating “application has data”. | **None** – same reason; QUIC frames only appear after data has been selected for transmission. |
| **Endpoint observability** | API/metrics that report the *application‑side* pending byte count (e.g., custom kernel probes, `getsockopt` extensions). | Implementation‑specific instrumentation (e.g., `quic_socket_get_pending_bytes()`) or eBPF probes on the stream buffer. |
| **Derived / inferred?** | Must be **derived** from endpoint state; cannot be inferred from the wire alone. |
| **Research question** | *What information is required to know whether the application has pending data, and can an observer obtain that information from the endpoint?* |

### 2.2 FlowControlAllowsNewData (F)

| Aspect | TCP | QUIC |
|--------|-----|------|
| **Realization** | Effective remote credit = `AdvertisedWindow × ScalingFactor – BytesInFlight`.  New data may be sent only if this credit > 0.  The advertised window is the value carried in the latest ACK, after applying the Window‑Scale option (RFC 7323). |
| **QUIC** | QUIC carries a *max data* value per connection and per stream.  The sender’s available credit = `remote_max_data – bytes_sent_in_flight`.  Values are negotiated in the handshake and updated via MAX_DATA / MAX_STREAM_DATA frames. |
| **Wire observability** | **Direct** – each ACK contains the raw 16‑bit Window field and the Window‑Scale option (if any).  The **effective credit** is *not* transmitted directly; it must be reconstructed using the scaling factor and the amount of data known to be in flight. |
| **QUIC wire** | **Direct** – MAX_DATA and MAX_STREAM_DATA frames are transported in cleartext (or after decryption for QUIC) and contain the current credit limits.  The *effective* credit still needs the sender’s current flight size to be subtracted. |
| **Endpoint observability** | The kernel stores the effective credit (e.g., `tcp_sock->rcv_wnd` after scaling) and can expose it via `TCP_INFO.tcpi_rcv_space` or via `getsockopt`. |
| **QUIC endpoint** | QUIC stack internal variables (e.g., `conn->flow_control.send_window`). May be exposed via library callbacks or eBPF probes. |
| **Derived / inferred?** | **Derived** on the wire (needs scaling factor and flight‑size estimation). **Direct** at the endpoint (effective credit is already computed). |
| **Research question** | *Can an observer reconstruct the effective flow‑control credit solely from the TCP/QUIC wire, or is endpoint state required?* |

### 2.3 CongestionControlAllowsNewData (C)

| Aspect | TCP | QUIC |
|--------|-----|------|
| **Realization** | The sender’s congestion‑control algorithm maintains a **congestion window** (cwnd) and a **flight size**.  The algorithm permits sending new data when `flight_size < cwnd` (or when the algorithm’s specific gating rule permits a probe packet).  The exact rule depends on the algorithm (CUBIC, Reno, BBR, etc.). |
| **QUIC** | QUIC re‑uses the same congestion‑control abstractions defined for TCP (cwnd, flight size).  The algorithm may be identical (CUBIC, BBR) or customized, but the decision rule is analogous: new data may be sent if the algorithm’s internal “budget” is positive. |
| **Wire observability** | **Indirect** – cwnd is never transmitted.  An observer may *infer* congestion state from patterns such as duplicate ACKs, loss events, RTT increase, or packet‑spacing, but cannot directly read cwnd. |
| **QUIC wire** | **Indirect** – same as TCP; QUIC does not expose cwnd on the wire.  Loss‑related frames (ACK ranges, ACK_ECN) can be used to infer congestion, but not directly. |
| **Endpoint observability** | The kernel holds `cwnd` in `tcp_sock->snd_cwnd` (or similar) and may expose it via `TCP_INFO.tcpi_snd_cwnd` or via custom probes. |
| **QUIC endpoint** | QUIC implementation stores `cwnd` in its connection object; libraries often expose it through APIs or can be instrumented with eBPF. |
| **Derived / inferred?** | Must be **derived** from endpoint state; wire can only provide *probabilistic* inference. |
| **Research question** | *Is the congestion‑control allowance predicate observable from the wire alone, or does it require endpoint‑internal state?* |

### 2.4 InRecovery (R)

| Aspect | TCP | QUIC |
|--------|-----|------|
| **Realization** | The sender enters a recovery mode after loss detection (e.g., three duplicate ACKs, SACK‑based detection, or retransmission timeout).  While in recovery, the algorithm may limit new data (only retransmissions, limited probing). |
| **QUIC** | QUIC defines a *recovery* state in the same way (RFC 9002 §7.2); loss detection triggers a recovery mode with similar restrictions. |
| **Wire observability** | **Indirect** – loss events are *implied* by duplicate ACKs, SACK blocks, or retransmitted sequence numbers.  The fact that the sender has entered *recovery* cannot be observed directly; only its *effects* (e.g., a burst of retransmissions, or the absence of new data) are visible. |
| **QUIC wire** | Same as TCP – loss‑related frames (ACK, SACK) can be observed, but the internal flag is not transmitted. |
| **Endpoint observability** | The kernel sets a recovery flag (`TCP_CA_Recovery`, `tcpi_recovery_state`) which can be read via `TCP_INFO` or via eBPF. |
| **QUIC endpoint** | QUIC stacks keep a recovery flag in the connection object; can be exposed via library callbacks or probes. |
| **Derived / inferred?** | **Derived** from endpoint for a definitive answer; wire can only provide *evidence* of loss, not the flag itself. |
| **Research question** | *Can an observer reliably decide that the sender is in a loss‑recovery phase from passive packet capture, or must endpoint information be consulted?* |

---

## 3. Predicate–Evidence Mapping (Research Questions)

| Predicate | Minimal evidence needed | Wire (TCP) | Wire (QUIC) | Endpoint (TCP) | Endpoint (QUIC) | Sufficient on wire? |
|-----------|------------------------|------------|-------------|----------------|-----------------|----------------------|
| **A** (HasPendingApplicationData) | Knowledge of whether the application has queued bytes *outside* the transport’s send queue. | ❌ – no packet carries this info. | ❌ | ✅ – socket‑level APIs or custom probes can report pending bytes. | ✅ – library‑level APIs or probes. | **No** |
| **F** (FlowControlAllowsNewData) | Effective remote credit *after scaling* and after subtracting in‑flight data. | ✅ – ACK Window field + Window‑Scale option (needs scaling). *Derived* (requires flight‑size estimate). | ✅ – MAX_DATA / MAX_STREAM_DATA frames (explicit values). *Derived* (requires flight‑size). | ✅ – endpoint already computes effective credit. | ✅ – endpoint directly knows it. | **No** (needs derivation) |
| **C** (CongestionControlAllowsNewData) | Algorithmic allowance (cwnd vs flight size) per the congestion algorithm. | ❌ – cwnd not on wire; only loss patterns can be *inferred*. | ❌ – same. | ✅ – cwnd variable exposed by kernel / stack. | ✅ – cwnd variable exposed by QUIC implementation. | **No** |
| **R** (InRecovery) | Flag indicating loss‑recovery mode. | ❌ – can only infer from loss evidence (duplicate ACKs, SACK holes). | ❌ – same. | ✅ – explicit recovery flag in kernel / QUIC stack. | ✅ – explicit recovery flag. | **No** (only indirect inference) |

*“Derived”* means the observer must perform a calculation (e.g., apply the scaling factor to the TCP Window field and subtract the estimated flight size) to obtain the predicate’s truth value.

---

## 4. State Machine (Layer 1)

```text
                +--------------------+
                |      READY         |
                | A ∧ F ∧ C ∧ ¬R    |
                +----------+---------+
                           |
            +--------------+--------------+--------------+--------------+
            |              |              |              |
            v              v              v              v
   +----------------+ +----------------+ +----------------+ +-----------------+
   | APPLICATION_   | | RECEIVER_FLOW_ | | CONGESTION_    | | MULTIPLE_       |
   | LIMITED        | | CONTROL_       | | CONTROL_       | | LIMITERS        |
   | ¬A ∧ F ∧ C ∧ ¬R| | A ∧ ¬F ∧ C ∧ ¬R| | A ∧ F ∧ ¬C ∧ ¬R| | A ∧ (¬F ∧ ¬C) ∧ ¬R|
   +----------------+ +----------------+ +----------------+ +-----------------+
            \              |              /            /
             \             |             /            /
              \            |            /            /
               \           |           /            /
                v          v          v            v
                +------------------------------+
                |   INSUFFICIENT_EVIDENCE      |
                |   (cannot evaluate one or    |
                |    more predicates)          |
                +------------------------------+
```

Recovery (`R`) is orthogonal: it may be true in any of the above states,
yielding composite descriptions such as “READY + R” or
“CONGESTION_CONTROL_LIMITED + R”.

*Transitions* occur whenever any predicate changes its truth value (e.g., an
`APP_DATA_AVAILABLE` event toggles `A`; a `FLOW_CONTROL_UPDATE` toggles `F`;
a `LOSS_DECLARED` toggles `R`; a `PKT_SENT`/`ACK_PROCESSED` may cause `C`
to change).  When more than one limiting predicate is false simultaneously,
the system moves to **MULTIPLE_LIMITERS**.  If the observer cannot determine
the value of a predicate (e.g., missing ACKs, no access to endpoint counters),
the state becomes **INSUFFICIENT_EVIDENCE**.

---

## 5. Event ⇢ Predicate Updates (Layer 1)

| Event | Predicates potentially affected | Typical effect |
|-------|--------------------------------|----------------|
| **APP_DATA_AVAILABLE** | `A` | Sets `A = true` (if data was previously absent). |
| **PKT_SENT** | `C` (reduces remaining congestion credit), `F` (reduces remote credit), `A` (may reduce pending data if buffer emptied). |
| **ACK_PROCESSED** | `C` (may increase remaining congestion credit), `F` (may increase remote credit), `A` (no effect). |
| **LOSS_DECLARED** | `R` (sets true), `C` (may shrink congestion allowance). |
| **FLOW_CONTROL_UPDATE** | `F` (re‑computes remote credit). |

---

## 6. Verification Flags (to be checked against Linux / QUIC implementations)

| # | Assumption to verify | Why it matters |
|---|----------------------|----------------|
| **V‑1** | “Data already placed in the kernel’s send buffer counts as *pending* application data.” | Incorrect – pending data must be *pre‑send* (see `A` definition). |
| **V‑2** | “A zero TCP Window field (`rwnd == 0`) is the sole condition for flow‑control limitation.” | Incorrect – effective credit depends on scaling and on flight size; `F` must consider the *effective* credit, not the raw field. |
| **V‑3** | “`cwnd - BytesInFlight <= 0` directly defines congestion‑control limitation.” | Incorrect – this is part of the **TCP realization** of `C`; the semantic predicate `C` is purely “algorithm permits sending”. |
| **V‑4** | “`SO_SNDBUF` occupancy equals pending application data.” | Incorrect – `SO_SNDBUF` is the buffer *capacity*; occupancy may be zero while the application still has data queued elsewhere. |
| **V‑5** | “The latest raw TCP Window field equals the exact usable sender credit.” | Incorrect – must apply the Window‑Scale factor and subtract in‑flight bytes to obtain usable credit. |
| **V‑6** | “Limiting causes are mutually exclusive.” | Incorrect – the model includes **MULTIPLE_LIMITERS** and permits overlapping predicates. |

These flags must be validated against the kernel source (`net/ipv4/tcp*`,
`include/linux/tcp.h`) and against QUIC library source (e.g., `quic-go`,
`MsQuic`, `ngtcp2`) before any concrete implementation.

---

## 7. References (protocol specifications)

| RFC | Title |
|-----|----------------------------------------------|
| **RFC 9293** | *Transmission Control Protocol (TCP)* – core TCP spec. |
| **RFC 5681** | *TCP Congestion Control* – cwnd, slow start, recovery. |
| **RFC 7323** | *TCP Extensions for High Performance* – Window scaling, timestamps. |
| **RFC 2018** | *TCP Selective Acknowledgment Options* – SACK. |
| **RFC 6298** | *Computing TCP Retransmission Timer* – RTO. |
| **RFC 9002** | *QUIC Loss Detection and Congestion Control* – QUIC recovery and cwnd. |
| **RFC 9000** | *QUIC Transport Protocol* – flow‑control signaling (MAX_DATA, MAX_STREAM_DATA). |
| **RFC 9221** | *QUIC Datagram Frames* – optional datagram flow‑control. |

---

### End of Document

*This document contains only the logical model and the mapping tables; no
experiments have been executed and no system‑changing commands have been run.*

