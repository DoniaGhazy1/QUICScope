# Verification of the Four TCP‑Semantic Predicates

Below is a systematic, four‑step analysis for each of the predicates that compose the frozen diagnostic state‑machine:

* **HasTransportPendingData** – there is unsent (but already handed to the transport) payload.
* **FlowControlAllowsNewData** – the receiver’s advertised credit is sufficient for at least one new byte.
* **CongestionControlAllowsNewData** – the sender’s congestion‑control algorithm permits transmission.
* **InRecovery** – the sender is currently in a loss‑recovery phase.

For every predicate we:

1. **STEP 1 – TCP specification** – locate the relevant RFC text, name the TCP state variables and rules that the RFC defines.
2. **STEP 2 – Wire observability** – indicate which of those variables appear verbatim in TCP headers/options (WIRE_DIRECT), which can be reconstructed from a complete packet trace (WIRE_DERIVED), and which are never transmitted (NOT_WIRE_OBSERVABLE).
3. **STEP 3 – Linux realization** – map the RFC concept onto concrete kernel structures, fields, functions, and the public measurement interfaces (`TCP_INFO`, `ss`, `/proc/net/tcp`).  For each candidate we give the source file/function that implements or exposes it.
4. **STEP 4 – Verification requirement** – classify each candidate as **UNVERIFIED_CANDIDATE**, **SOURCE_SUPPORTED_CANDIDATE**, or **READY_FOR_EXPERIMENTAL_VALIDATION**.

> **Notation** – All RFC references are to the latest stable specifications (RFC 9293, RFC 5681, RFC 6298, RFC 7323, RFC 896).  Section numbers are taken from the PDF/HTML version of each RFC.

---

## 1. HasTransportPendingData

### STEP 1 – TCP Specification

| RFC | Section | Quote / Concept |
|-----|---------|-----------------|
| **RFC 9293** (TCP) | **3.9.  Send Sequence Variables** | “`SND.UNA` – the oldest unacknowledged sequence number. <br>`SND.NXT` – the next sequence number to be sent.” |
| RFC 9293 | **3.5.  Transmission Control Block** | The send buffer holds data not yet transmitted; the amount of data “in the send queue” is `SND.NXT – SND.UNA` (data that has been placed on the wire) plus any data queued in the socket that has not yet been assigned a sequence number. |
| RFC 896 (Congestion Control) | **2** | “A sender MUST NOT send data if it has no data to send.” – i.e. the sender must have data pending in its socket queue before it can progress. |

**TCP‑level definition of the predicate**: *There exists at least one byte that the application has already handed to the TCP layer (i.e. it resides in the socket’s send buffer) but that has not yet been transmitted on the wire.*

The RFC does **not** provide a named variable for this “unsent‑but‑queued” amount; it is implicitly the data that resides in the socket’s write queue and has not yet been incorporated into `SND.NXT`.

### STEP 2 – Wire Observability

| Category | Information | Remarks |
|----------|-------------|---------|
| **WIRE_DIRECT** | `SEQ` numbers of data segments (gives the highest sequence number that *has* been placed on the wire → a lower bound on `SND.NXT`). | No field indicates how many bytes are still waiting in the socket’s write queue. |
| **WIRE_DERIVED** | `SND.UNA` – inferred from the most recent cumulative ACK (`ACK` field). <br>`flight = SND.NXT – SND.UNA` – derived from the highest observed `SEQ` and the latest `ACK`. | This yields the *in‑flight* portion but **does not** reveal the bytes that are pending in the kernel but not yet assigned a sequence number. |
| **NOT_WIRE_OBSERVABLE** | Exact size of the socket’s *unsent* (still‑queued) data. <br>Whether the socket’s write queue contains data that has not yet been given a sequence number (`write_seq` vs. `snd_nxt`). | The TCP stack never transmits this count. |

### STEP 3 – Linux Realisation

| Predicate | RFC‑concept | Linux structure / field / function | Source file (approx.) | Public measurement / exposure |
|-----------|-------------|-----------------------------------|----------------------|------------------------------|
| **HasTransportPendingData** | “Data queued in the socket’s send buffer” | `struct tcp_sock` → `write_seq` (next byte the application will write) <br>`snd_nxt` (next byte to be transmitted) <br>`sk->sk_wmem_queued` (total bytes queued in the socket write buffer) | `include/net/tcp.h` (definition of `struct tcp_sock`) <br>`net/ipv4/tcp_output.c` (updates of `write_seq`, `snd_nxt`) | `getsockopt(sock, SOL_TCP, TCP_INFO, …)` → fields: <br>• `tcpi_unacked` (segments with seq ≤ `snd_nxt` not yet ACKed) <br>• `tcpi_notsent_bytes` (bytes written but not yet transmitted; available on kernels ≥ 5.10) <br>• `tcpi_snd_nxt`, `tcpi_snd_una` <br>`ss -tin` → “send‑Q” column (bytes pending in kernel) <br>`/proc/net/tcp` via netlink (`snd_wnd`, `snd_nxt`, `snd_una`, `write_seq`) |

### STEP 4 – Verification Requirement

| Candidate | Classification | Reasoning |
|-----------|----------------|-----------|
| `tcpi_notsent_bytes` (TCP_INFO) | **SOURCE_SUPPORTED_CANDIDATE** | Source code (`net/ipv4/tcp_output.c`, `tcp_get_info()`) explicitly documents that this field reports “the amount of data written to the socket but not yet transmitted”. Still needs a controlled experiment to confirm that it matches the semantic predicate in all corner cases (e.g., zero‑copy sends, TSO). |
| `tcpi_unacked` | **UNVERIFIED_CANDIDATE** | Counts un‑ACKed *segments*; conflates in‑flight data with data that may already have been transmitted. It does **not** differentiate data that is still queued but not yet assigned a sequence number. |
| `sk->sk_wmem_queued` (exposed via `ss -tin` “send‑Q”) | **UNVERIFIED_CANDIDATE** | Represents total socket write‑memory usage, which includes protocol headers and other bookkeeping; unclear how directly it maps to “application payload pending”. |
| `write_seq – snd_nxt` (computed from kernel structures) | **SOURCE_SUPPORTED_CANDIDATE** | The variables exist in the kernel and their difference is exactly the “bytes not yet sent”. No public API directly exposes the diff, but it can be derived from two TCP‑INFO fields (`tcpi_snd_nxt` and a hypothetical `tcpi_write_seq` if exported). Needs a measurement path. |

---

## 2. FlowControlAllowsNewData

### STEP 1 – TCP Specification

| RFC | Section | Quote / Concept |
|-----|---------|-----------------|
| **RFC 9293** | **3.9.  Send Sequence Variables** | “`SND.WND` – the size of the send window; the sender may transmit data up to `SND.UNA + min(SND.WND, RCV.WND)`.” |
| **RFC 7323** (Window Scaling) | **2.2** | “The Window field is multiplied by the scaling factor announced in the Window‑Scale option (a power of two).” |
| **RFC 9293** | **3.10.  Receive Sequence Variables** | “`RCV.WND` – the receive window advertised to the peer (in the ACK).” |
| **RFC 9293** | **4.2.  Form of a Segment** | The ACK segment carries the **Window** field (16‑bit) and, after the handshake, a **Window‑Scale** option (if negotiated). |

**TCP‑level definition of the predicate**: *The remote endpoint has advertised enough receive credit such that, after accounting for scaling and for bytes already in flight, the sender could transmit at least one additional byte.*

Mathematically (RFC 9293, §3.9):

```
usable_credit = min(SND.WND, advertised_window) - (SND.NXT – SND.UNA)
```

The predicate is true iff `usable_credit > 0`.

### STEP 2 – Wire Observability

| Category | Information | Remarks |
|----------|-------------|---------|
| **WIRE_DIRECT** | `Window` field in every ACK segment (16‑bit raw advertised window). <br>`Window‑Scale` option in the SYN/SYN‑ACK (negotiated exponent). | The raw `Window` value alone is insufficient; the scale factor must be remembered from the handshake. |
| **WIRE_DERIVED** | `advertised_window_scaled = Window << scale_factor`. <br>`SND.UNA` and `SND.NXT` derived as in predicate 1. <br>`flight = SND.NXT – SND.UNA`. <br>`usable_credit = advertised_window_scaled – flight`. | This reconstruction assumes a loss‑free trace; duplicate ACKs, reordered packets, or missing packets will corrupt the calculation. |
| **NOT_WIRE_OBSERVABLE** | The *effective* send window that the kernel stores after applying scaling and after subtracting the flight size (`snd_wnd` after scaling). | The kernel may keep an internally cached value that differs from the instantaneous raw `Window` field due to delayed ACK handling, scaling updates, or window‑shrinking events. |

### STEP 3 – Linux Realisation

| Predicate | RFC‑concept | Linux structure / field / function | Source file (approx.) | Public measurement / exposure |
|-----------|-------------|-----------------------------------|----------------------|------------------------------|
| **FlowControlAllowsNewData** | Remote advertised receive window (`RCV.WND`), scaling factor, flight size. | `struct tcp_sock` → `rcv_wnd` (scaled receive window as stored by the receiver), `snd_wscale` (sender‑side window‑scale exponent), `snd_wnd` (remote‑advertised window after scaling), `snd_nxt`, `snd_una`. | `include/net/tcp.h` (fields) <br>`net/ipv4/tcp_input.c` (updates of `rcv_wnd`, `snd_wnd`) | `getsockopt(sock, SOL_TCP, TCP_INFO, …)` → `tcpi_snd_wnd` (effective window *in bytes*). <br>`ss -ti` → column `snd_wnd`. <br>`/proc/net/tcp` netlink dump → `snd_wnd` (scaled). |

### STEP 4 – Verification Requirement

| Candidate | Classification | Reasoning |
|-----------|----------------|-----------|
| `tcpi_snd_wnd` (TCP_INFO) | **SOURCE_SUPPORTED_CANDIDATE** | The TCP_INFO documentation (and `tcp_get_info()` source) says this field reports “the size of the sending window” after scaling and after subtracting flight size. Still needs experimental validation that it matches the RFC‑defined `usable_credit`. |
| `snd_wnd` (struct tcp_sock) | **SOURCE_SUPPORTED_CANDIDATE** | Directly stores the remote‑advertised window after scaling; internal to kernel, never sent on wire. |
| `rcv_wnd` (struct tcp_sock) | **UNVERIFIED_CANDIDATE** | Holds the receiver’s *own* window; relevant only for the opposite direction, not for the sender’s flow‑control allowance. |
| `snd_wscale` (struct tcp_sock) | **UNVERIFIED_CANDIDATE** | The scaling exponent is negotiated in the SYN; the field is used by the kernel to compute the effective window, but the public interface does not expose the exponent directly (except via `TCP_INFO` on newer kernels). |

---

## 3. CongestionControlAllowsNewData

### STEP 1 – TCP Specification

| RFC | Section | Quote / Concept |
|-----|---------|-----------------|
| **RFC 5681** (TCP Congestion Control) | **3.1.  Congestion Window (cwnd)** | “`cwnd` limits the amount of data the sender may have in flight. The sender may send new data if **bytes_in_flight < cwnd**.” |
| RFC 5681 | **3.2.  Slow Start** – explanation of how `cwnd` grows. |
| RFC 6298 (RTO) | **2.2** – mentions that retransmission events affect `cwnd`. |
| RFC 9293 | **3.9** – defines `bytes_in_flight = SND.NXT – SND.UNA`. |

**TCP‑level definition of the predicate**: *The sender’s congestion‑control algorithm permits the transmission of new data iff the current flight size (`SND.NXT – SND.UNA`) is strictly less than the current congestion window (`cwnd`).*  Mathematically: `cwnd > (SND.NXT – SND.UNA)`.

### STEP 2 – Wire Observability

| Category | Information | Remarks |
|----------|-------------|---------|
| **WIRE_DIRECT** | None. The TCP header does **not** carry `cwnd` or any congestion‑control flag. |
| **WIRE_DERIVED** | `SND.UNA` and `SND.NXT` can be derived from ACK and data SEQ numbers (as in predicate 1). Thus the *flight size* can be reconstructed, but the *cwnd* value itself cannot. |
| **NOT_WIRE_OBSERVABLE** | The current congestion window (`cwnd`) – a local algorithmic state kept inside the kernel. Also the current slow‑start threshold (`ssthresh`), which influences `cwnd` updates, is invisible on the wire. |

### STEP 3 – Linux Realisation

| Predicate | RFC‑concept | Linux structure / field / function | Source file (approx.) |
|-----------|-------------|-----------------------------------|------------------------|
| **CongestionControlAllowsNewData** | `cwnd` – congestion window, `bytes_in_flight` – `snd_nxt – snd_una` | `struct tcp_sock` → `snd_cwnd` (in *segments*), `snd_ssthresh`, `snd_mss` (MSS, to translate cwnd to bytes). <br>Functions that compute/adjust cwnd: `tcp_cong_avoid()`, `tcp_cwnd_validation()`, `tcp_set_ca_state()` (found in `net/ipv4/tcp_output.c`, `net/ipv4/tcp_cong.c`). | `include/net/tcp.h` (field definitions) <br>`net/ipv4/tcp_output.c` (cwnd updates) <br>`net/ipv4/tcp_cong.c` (congestion‑control algorithms) |
| **Public measurement** | – | `getsockopt(TCP_INFO)` → `tcpi_snd_cwnd` (in *segments*). <br>`ss -ti` → column `cwnd` (bytes). <br>`/proc/net/tcp` netlink dump → `snd_cwnd`. |

### STEP 4 – Verification Requirement

| Candidate | Classification | Reasoning |
|-----------|----------------|-----------|
| `tcpi_snd_cwnd` (TCP_INFO) | **SOURCE_SUPPORTED_CANDIDATE** | The kernel source (`tcp_get_info()`) populates this field from `tp->snd_cwnd * tp->snd_mss`. Explicit mapping to the RFC’s `cwnd`. Still requires experiments to confirm that the *effective* bytes‑in‑flight comparison (`cwnd > flight`) matches the predicate under all congestion‑control algorithms. |
| `snd_cwnd` (struct tcp_sock) | **SOURCE_SUPPORTED_CANDIDATE** | Direct internal representation of congestion window. |
| `snd_ssthresh` (struct tcp_sock) | **UNVERIFIED_CANDIDATE** | Not needed for the Boolean predicate, but part of cwnd dynamics. |
| `tcpi_snd_mss` (TCP_INFO) | **UNVERIFIED_CANDIDATE** | Required to translate `cwnd` segments to bytes; the kernel documentation says it’s the *maximum segment size* the sender can use. The relationship to the predicate is indirect. |

---

## 4. InRecovery

### STEP 1 – TCP Specification

| RFC | Section | Quote / Concept |
|-----|---------|-----------------|
| **RFC 5681** | **3.4.  Fast Recovery** | “If three duplicate ACKs arrive, the sender enters *fast recovery*; cwnd is set to `ssthresh + 3·SMSS` and the sender may transmit new data while awaiting further ACKs.” |
| **RFC 6298** (RTO) | **2.2** | “If the retransmission timer expires, the sender enters *recovery* (often called *timeout recovery*).” |
| **RFC 9293** | **3.5.  Retransmission Timeout (RTO)** | Describes the transition to **retransmission** and the setting of the **recovery** state. |
| **RFC 2582** (Selective ACK) | **3** | Presence of SACK blocks may trigger a recovery phase. |

**TCP‑level definition of the predicate**: *The sender is in a loss‑recovery phase (fast‑recovery, selective‑ACK recovery, or timeout‑based retransmission). The connection’s internal *recovery* flag (`CA_Recovery` etc.) is set.*

The RFC does **not** expose a wire‑level flag; recovery is inferred from events (duplicate ACKs, SACKs, retransmissions).

### STEP 2 – Wire Observability

| Category | Information | Remarks |
|----------|-------------|---------|
| **WIRE_DIRECT** | None – the TCP header never carries a “recovery‑mode” flag. |
| **WIRE_DERIVED** | Patterns that *suggest* recovery: <br>• Three duplicate ACKs (same `ACK` number, no new data). <br>• Presence of SACK blocks indicating selective ACK of non‑contiguous data. <br>• Retransmission of a segment whose sequence number has already been seen (re‑sent data). | Such patterns can be detected from a full trace, but they only *suggest* that the sender has entered a recovery routine. The sender may still be in normal mode if the duplicate ACKs are caused by reordering rather than loss. |
| **NOT_WIRE_OBSERVABLE** | The explicit internal recovery state (`TCP_CA_Recovery`, `TCP_CA_Disorder`, `TCP_CA_CWR`). The kernel’s decision *when* to exit recovery (e.g., on new ACK that acknowledges all data) is also local. |

### STEP 3 – Linux Realisation

| Predicate | RFC‑concept | Linux structure / field / function | Source file (approx.) |
|-----------|-------------|-----------------------------------|------------------------|
| **InRecovery** | “Recovery flag” (fast‑recovery, timeout recovery) | `struct tcp_sock` → `ca_state` (enum `tcp_ca_state`: `TCP_CA_Open`, `TCP_CA_Disorder`, `TCP_CA_CWR`, `TCP_CA_Recovery`). <br>Also `tp->retrans_out` (outstanding retransmissions). <br>Functions that set the state: `tcp_enter_recovery()`, `tcp_enter_cwr()`, `tcp_fastretrans_alert()`. | `include/net/tcp.h` (enum definition) <br>`net/ipv4/tcp_input.c` (calls to `tcp_enter_recovery()`) <br>`net/ipv4/tcp_output.c` (recovery handling) |
| **Public measurement** | – | `getsockopt(TCP_INFO)` → `tcpi_recovery_state` (numeric code matching `enum tcp_ca_state`). <br>`ss -ti` → `state` column (shows `CA_Recovery`, `CA_Disorder`, etc.). <br>`/proc/net/tcp` netlink dump → field `recovery_state`. |

### STEP 4 – Verification Requirement

| Candidate | Classification | Reasoning |
|-----------|----------------|-----------|
| `tcpi_recovery_state` (TCP_INFO) | **SOURCE_SUPPORTED_CANDIDATE** | Kernel source (`tcp_get_info()`) fills this from `tp->ca_state`. The mapping to the RFC’s “in recovery” boolean is clear, but the field may contain several values (Open, Disorder, CWR, Recovery). Still needs a test that confirms which of those constitute “in recovery” for the predicate (likely any non‑Open state). |
| `ca_state` (struct tcp_sock) | **SOURCE_SUPPORTED_CANDIDATE** | Direct internal representation; the enum values are documented in the kernel source. Still needs a test that verifies that, e.g., `TCP_CA_Disorder` truly corresponds to the RFC‑defined “recovering from out‑of‑order packets”. |
| Duplicate‑ACK detection in the trace (derived) | **UNVERIFIED_CANDIDATE** | Although derived from the wire, a detection algorithm must be built and checked against the kernel’s flag to see whether the inference is always correct. |
| `retrans_out` counter | **UNVERIFIED_CANDIDATE** | The kernel increments this during retransmissions; however, a non‑zero value does not necessarily mean the sender is still in the recovery phase (it may have already exited). |

---

# Consolidated Summary Table

| Predicate | RFC‑defined TCP concept | Required information (per‑connection) | Wire‑direct | Wire‑derived | Missing from wire | Linux candidate (measurement) | Source evidence (file/field) | Experiment needed to validate |
|-----------|------------------------|--------------------------------------|-------------|--------------|-------------------|------------------------------|------------------------------|--------------------------------|
| **HasTransportPendingData** | “Data queued in the socket’s send buffer but not yet transmitted” (RFC 9293 §3.5) | `write_seq` – bytes written by the app <br>`snd_nxt` – next seq to send <br>`snd_una` – oldest un‑ACKed seq <br>socket write‑queue length | `SEQ` (data packets) <br>`ACK` (ack packets) | `snd_una` from ACKs <br>`flight = snd_nxt – snd_una` | Exact unsent‑queue size (`write_seq – snd_nxt`) – never on wire | `tcpi_notsent_bytes` (TCP_INFO) <br>`tcpi_unacked` (TCP_INFO) <br>`ss -tin` “send‑Q” | `net/ipv4/tcp_output.c` (`tcp_get_info()` fills `tcpi_notsent_bytes`) <br>`include/net/tcp.h` fields | Controlled experiment that writes a known amount of data to a socket, then pauses the sender (e.g., via `tc qdisc` or congestion‑window limit) and compares the kernel‑reported values against the ground‑truth amount of queued bytes. |
| **FlowControlAllowsNewData** | “Sender may transmit if usable credit > 0” (RFC 9293 §3.9, RFC 7323 §2.2) | Remote advertised window (`Window` field) <br>Negotiated window‑scale <br>`snd_una`, `snd_nxt` (flight) | `Window` field in ACKs <br>`Window‑Scale` option in SYN/SYN‑ACK | `advertised_window_scaled = Window << scale` <br>`flight = snd_nxt – snd_una` <br>`usable_credit = advertised_window_scaled – flight` | Effective send‑window after scaling and flight subtraction (kernel’s `snd_wnd`) – not sent on wire | `tcpi_snd_wnd` (TCP_INFO) <br>`ss -ti` column `snd_wnd` | `include/net/tcp.h` (`tp->snd_wnd`) <br>`net/ipv4/tcp_input.c` updates `tp->snd_wnd` | Experiment that varies the advertised window (e.g., using `setsockopt(SO_RCVBUF)` on the receiver) while the sender is idle, then checks that `tcpi_snd_wnd` matches the expected scaled value and that the predicate flips exactly when `usable_credit` crosses zero. |
| **CongestionControlAllowsNewData** | “Transmit if bytes_in_flight < cwnd” (RFC 5681 §3.1) | `cwnd` (congestion window) <br>`snd_nxt`, `snd_una` (flight) | *none* | `flight = snd_nxt – snd_una` (derived) | Current `cwnd` (and possibly `ssthresh`) – never on wire | `tcpi_snd_cwnd` (TCP_INFO) <br>`ss -ti` column `cwnd` | `include/net/tcp.h` (`tp->snd_cwnd`) <br>`net/ipv4/tcp_output.c` (`tcp_cwnd_validate()`) | Experiment that forces a known congestion‑window size (e.g., by configuring a simple loss‑inducing path or by fixing the congestion‑control algorithm to a known state) and verifies that `tcpi_snd_cwnd` reports the exact value; also verify the predicate’s Boolean outcome against the ground‑truth inequality. |
| **InRecovery** | “Sender is in loss‑recovery (fast‑recovery, SACK‑recovery, timeout‑recovery)” (RFC 5681 §3.4, RFC 6298 §2) | Current recovery state (`TCP_CA_Recovery`, `TCP_CA_Disorder`, `TCP_CA_CWR`) <br>Optional: counters of duplicate ACKs, SACK blocks, retransmissions | *none* (no explicit flag) | Duplicate‑ACK patterns, SACK blocks, retransmitted seq numbers (derived) | Internal recovery flag (`ca_state`) – not transmitted | `tcpi_recovery_state` (TCP_INFO) <br>`ss -ti` column `state` (shows `CA_Recovery` etc.) | `include/net/tcp.h` (`enum tcp_ca_state`) <br>`net/ipv4/tcp_input.c` (`tcp_enter_recovery()`) | Experiment that deliberately triggers fast‑recovery (e.g., by dropping three consecutive packets) and confirms that the kernel’s `tcpi_recovery_state` changes to the expected enum, while also checking that the derived duplicate‑ACK pattern matches the kernel flag. |

---

## Remaining Open Issues

1. **Exact semantics of “unsent”** – Linux provides `tcpi_notsent_bytes` only on recent kernels; older kernels lack a dedicated field, forcing a composite measurement (`write_seq – snd_nxt`). The precise definition (bytes waiting for segmentation, TSO, or NIC‑level queue) needs clarification.
2. **Window‑scale persistence** – If a capture starts after the three‑way handshake, the scaling exponent must be recovered from the initial SYN/SYN‑ACK; missing this information would break the `advertised_window_scaled` calculation.
3. **cwnd units** – `tcpi_snd_cwnd` reports *segments*; converting to bytes requires the current MSS (`tcpi_snd_mss`). MSS can change during a connection (path‑MTU discovery), so the conversion must use the live value.
4. **Recovery‑state granularity** – Linux distinguishes several recovery sub‑states (`Disorder`, `CWR`, `Recovery`). The semantic predicate asks only for a Boolean “in recovery”. Deciding which enum values qualify (likely any non‑Open state) must be formalised before experimental validation.
5. **Trace completeness** – Wire‑derived quantities assume loss‑free, ordered capture. In practice, missing packets (e.g., due to sampling or hardware drops) will corrupt `snd_una` / `snd_nxt` reconstruction, potentially leading to false predicate evaluations. Any experimental design must therefore ensure a *complete* bidirectional capture.

These items define the next‑step research tasks before the actual controlled experiments can be performed.
