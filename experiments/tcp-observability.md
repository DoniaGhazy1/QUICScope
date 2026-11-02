# TCP Observability – Information Required for the Four Predicates

The following table summarizes, for each of the four Layer 1 predicates, the
exact pieces of information needed to decide the predicate, what can be
obtained directly from a TCP packet capture, what can be derived from the
capture, and what must be sourced from the host (Linux) endpoint.  It also
states the concrete Linux interface or tool that can expose the missing data
and whether that measurement is per‑connection (socket) or system‑wide.

| Predicate | Required information (per‑connection) | Wire‑direct (appears verbatim in a packet) | Wire‑derived (computed from captured packets) | Missing from wire (cannot be observed) | Linux endpoint candidate (tool / ioctl) | Scope |
|-----------|--------------------------------------|--------------------------------------------|-----------------------------------------------|------------------------------------------|------------------------------------------|-------|
| **HasTransportPendingData** | • Total bytes enqueued in the socket send buffer (including data not yet transmitted)  
• Bytes already transmitted but not yet ACKed (flight size)  
• Sequence numbers: `SND.UNA` (oldest un‑ACKed) and `SND.NXT` (next to send) | – `SEQ` of outgoing data packets (provides `SND.NXT` as the next sequence number)  
– `ACK` numbers in ACK packets (provide `SND.UNA`)  
– Payload length in data packets (helps compute how many bytes were transmitted) | • `SND.UNA` = last ACK number observed  
• `SND.NXT` = highest sequence number seen on the wire + 1  
• Flight size = `SND.NXT - SND.UNA` (bytes in flight) | • Exact send‑buffer occupancy (how many bytes are still waiting to be handed to the NIC)  
• Bytes that have been queued but not yet emitted on the wire (the *unsent* portion) | **getsockopt(TCP_INFO)** – fields `tcpi_unacked`, `tcpi_snd_nxt`, `tcpi_snd_una`, and on kernels ≥ 5.10 `tcpi_notsent_bytes`  
**ss -tin** – shows `send‑Q` (bytes pending in kernel)  
**/proc/net/tcp** (via netlink) – provides `snd_wnd`, `snd_nxt`, `snd_una`  
Both expose per‑socket state. | per‑connection |
| **FlowControlAllowsNewData** | • Remote advertised receive window (`rwnd`) as advertised in ACKs  
• Window‑scale factor (negotiated in the SYN)  
• `SND.UNA` and `SND.NXT` (to compute flight size)  
• Effective send‑window = `scaled_rwnd - (SND.NXT‑SND.UNA)` | – `Window` field in ACK packets (raw receive‑window)  
– `Window Scale` option in SYN/SYN‑ACK (scale factor)  
– `ACK` numbers (for `SND.UNA`)  
– `SEQ` numbers (for `SND.NXT`)  
– Flags & payload length (to know which packets carry data) | • Scale the raw `Window` using the negotiated window‑scale (derived)  
• Compute `flight = SND.NXT‑SND.UNA`  
• Effective credit = `scaled_rwnd - flight`  
• Determine if credit > 0 (predicate true) | None – assuming a *full* bidirectional capture, all needed items are observable or derivable. | No endpoint data strictly required, but for validation one can read `tcpi_snd_wnd` (effective window) from **TCP_INFO**. | per‑connection (optional) |
| **CongestionControlAllowsNewData** | • Congestion window (`cwnd`) as maintained by the sender  
• Flight size (`SND.NXT‑SND.UNA`)  
• Optional: MSS (to interpret cwnd in segments) | – `SEQ` / `ACK` numbers (derive flight size)  
– Payload length (to count bytes transmitted) | • Compute `flight = SND.NXT‑SND.UNA` from captures  
• Compare `flight` with `cwnd` (needs `cwnd`) | • Current `cwnd` value is not present on the wire. It is a local, algorithm‑specific state. | **getsockopt(TCP_INFO)** – field `tcpi_snd_cwnd` (in segments, can be multiplied by MSS)  
**ss -ti** – column `cwnd` (bytes)  
**/proc/net/tcp** via netlink (field `snd_cwnd`) | per‑connection |
| **InRecovery** | • TCP recovery state (e.g., `TCP_CA_Recovery`, `TCP_CA_Disorder`, `TCP_CA_CWR`)  
• Optional: detection of duplicate ACKs, SACK blocks, or retransmissions (wire hints) | – Flags indicating retransmission (same `SEQ` as earlier)  
– `SACK` option blocks in ACKs  
– Duplicate ACK numbers (same `ACK` value repeated) | • From a capture you can infer that the sender *might* be in recovery when you see three duplicate ACKs, fast‑retransmit, or a timeout‑based retransmission.  
• However inference is not provably equivalent to the kernel’s internal flag. | • The explicit recovery flag (`tcpi_recovery_state`) is never sent on the wire. | **getsockopt(TCP_INFO)** – field `tcpi_recovery_state`  
**ss -ti** – shows `state` column (e.g., `CA_Recovery`)  
**/proc/net/tcp** via netlink – field `recovery_state` | per‑connection |

---

### Remaining uncertainties / open questions

1. **Exact definition of “unsent” for `HasTransportPendingData`.**  Linux kernels expose `tcpi_notsent_bytes` only on newer kernels (≥ 5.10) and sometimes only when the socket is in the `TCP_CLOSE` state.  On older kernels we may need to combine `send‑Q` from `ss` with `tcpi_unacked` to approximate the unsent portion, but the semantics differ slightly.
2. **Window‑scale visibility in captures.**  The scale factor is negotiated once during the handshake.  If a capture starts after the handshake, the scale must be remembered from the SYN/SYN‑ACK; otherwise the remote window cannot be correctly interpreted.
3. **Reliability of wire‑derived flight size.**  Packet loss during capture (e.g., due to sampling or hardware drops) will corrupt the derived `SND.UNA`/`SND.NXT` values, leading to incorrect assessment of flow‑control or congestion‑control predicates.
4. **Granularity of `cwnd` from `TCP_INFO`.**  The kernel reports `tcpi_snd_cwnd` in *segments* (MSS units).  When the MSS changes (e.g., due to path MTU discovery), the conversion to bytes must use the current MSS (`tcpi_snd_mss`).
5. **Recovery state nuances.**  Linux defines several recovery‑related states (`TCP_CA_Disorder`, `TCP_CA_CWR`, `TCP_CA_Recovery`).  The research question only needs a Boolean “in recovery”.  Mapping the enum to a Boolean is straightforward, but the precise transition points (e.g., after a single duplicate ACK) differ between implementations; the wire‑derived inference may not match the kernel’s state.

The table above captures the *minimum* set of observations required to evaluate
each predicate under the assumption of a loss‑free, bidirectional packet capture.
When any of the “Missing from wire” items cannot be obtained, the corresponding
Linux endpoint source must be consulted.
