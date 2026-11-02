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
what evidence is required to observe it.

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

---

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
