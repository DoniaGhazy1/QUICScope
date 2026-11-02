QUICScope Semantic Model (Revised)
1. Purpose and conventions
This document defines the semantic vocabulary used by experiments, instrumentation, and diagnosis. Definitions are independent of individual transport implementations. Where TCP and QUIC differ, each definition gives a TCP realization and a QUIC realization.
• Diagnosed endpoint: the sender of the data flow under diagnosis.
• States vs events: states are intervals [t_enter, t_exit); events are point samples. Every state signal must emit both enter and exit so durations are computable.
• Connection phase: HANDSHAKE | ONE_RTT | CLOSING. All classes are evaluated in ONE_RTT; AMPLIFICATION_LIMITED is also evaluated in HANDSHAKE.
• Minimum duration θ: a limiter state shorter than θ (default: one smoothed RTT, configurable) is recorded but not used for labeling, to suppress transient gates such as a single pacing gap. θ must be reported with results.
• Flow active: at least one stream is open, the handshake is confirmed, the connection is not closing or draining, and the send side is not finished on all streams. An idle connection is not app-limited unless it is flow-active.
2. Primitive quantities
Quantity
Definition
cwnd
Congestion window in bytes (RFC 9002 §7).
bif (bytes_in_flight)
Sum of sizes of sent packets that are in flight: ack-eliciting or containing PADDING, and not yet acknowledged, declared lost, or discarded. ACK-only packets are not in flight and not congestion controlled.
mss / next_pkt_size
Maximum datagram size, or the size of the next packet the sender would emit. State which is used.
app_off_s
Highest stream offset the application has written on stream s.
sent_off_s
Highest stream offset sent on stream s (new data only; retransmissions do not advance it).
fc_stream_limit_s
Largest MAX_STREAM_DATA received for s. Monotonic.
conn_sent / conn_limit
Sum of sent_off_s over streams / largest MAX_DATA received. Monotonic.
max_streams_{bidi,uni}
Largest MAX_STREAMS received per stream type.
Pending content classes (what the sender could emit):
• NEW(s): app_off_s > sent_off_s. This includes data that is flow-control blocked.
• RETX: stream or crypto data declared lost and queued for retransmission. It consumes no new flow-control credit (RFC 9000 §4.1, credit is counted by highest offset).
• CRYPTO: handshake data. Not subject to stream or connection flow control.
• DGRAM: DATAGRAM frames (RFC 9221). Congestion controlled, not flow controlled.
• CTRL: ack-eliciting control frames (e.g., MAX_DATA, MAX_STREAMS updates).
P(t) is the set of pending content classes at time t, regardless of any constraint.
3. Constraints and binding predicates
Each constraint has a content-free ROOM predicate (does the transport have capacity?) and a content-dependent ACTIVE predicate (is the constraint currently preventing transmission of something pending?). Several constraints may be active simultaneously. This replaces the original asymmetric 'not binding' / 'not primary' wording.
3.1 Congestion control (CC)
CC_ROOM(t)   ⇔ bif(t) + next_pkt_size ≤ cwnd(t)
CC_ACTIVE(t) ⇔ ¬CC_ROOM(t) ∧ P(t) contains a congestion-controlled class
               (NEW with credit, RETX, CRYPTO, DGRAM, ack-eliciting CTRL)
• RFC 9002 §7 allows exceeding cwnd for PTO probe packets and on entering recovery. Packets sent under these exceptions must carry probe=true and must not be used as evidence that CC is not active.
• Stacks differ in the gate: strict (bif + size ≤ cwnd) or lax (bif < cwnd). Record cc_gate = STRICT | LAX per stack.
• Record CC state alongside: SLOW_START | CONGESTION_AVOIDANCE | RECOVERY | PERSISTENT_CONGESTION.
• ECN-CE increases in ACK_ECN counts trigger a congestion event without loss (RFC 9002 §7.1). Record them as congestion events (§5.7).
3.2 Pacing (PACE)
PACE_ROOM(t)   ⇔ pacer_next_send_time ≤ t
PACE_ACTIVE(t) ⇔ ¬PACE_ROOM(t) ∧ CC_ROOM(t) ∧ P(t) contains a congestion-controlled class
• RFC 9002 §7.7 recommends pacing. Hook the pacer wait (timer armed or send deferred), not the rate computation.
• Pacing offload (GSO, kernel pacing via SO_TXTIME or fq) moves the gate outside the stack. Record pacing_mode = USERSPACE | KERNEL | OFFLOAD | NONE.
3.3 Anti-amplification (AMP)
AMP_ROOM(t)   ⇔ role ≠ server ∨ addr_validated ∨ bytes_sent + next_dgram_size ≤ 3 × bytes_received
AMP_ACTIVE(t) ⇔ ¬AMP_ROOM(t) ∧ P(t) ≠ ∅
• RFC 9000 §8.1. Counts UDP datagram payload bytes, not QUIC packets.
• Applies to all content classes, including probes. Interacts with PTO arming (RFC 9002 §6.2.2.1).
3.4 Stream-level flow control (FC_STREAM)
FC_STREAM_ACTIVE(s) ⇔ NEW(s) ∧ sent_off_s ≥ fc_stream_limit_s
FC_STREAM_ACTIVE    ⇔ ∃ s: NEW(s)  ∧  ∀ s with NEW(s): FC_STREAM_ACTIVE(s)
The second line is the connection-level roll-up: all streams with new data are stream-blocked. It applies only to NEW; RETX, CRYPTO, and DGRAM are unaffected.
3.5 Connection-level flow control (FC_CONN)
FC_CONN_ACTIVE ⇔ conn_sent ≥ conn_limit ∧ ∃ s: NEW(s)
Both FC_STREAM and FC_CONN may be active together (scope BOTH). A connection is not FC-limited merely because one stream is blocked: it is FC-limited only when no stream with new data is unblocked at both levels.
3.6 Stream-concurrency limit (STREAM_LIMIT)
STREAM_LIMIT_ACTIVE ⇔ app has requested to open a stream of type k with index ≥ max_streams_k,
                      and data intended for that stream is pending
MAX_STREAMS (RFC 9000 §4.6) is a credit mechanism distinct from MAX_DATA and MAX_STREAM_DATA. Hook trap: stack APIs may block, return an error, or queue the open request; the hook must capture the unsatisfied open, not the limit check.
3.7 Sendability and residual
SENDABLE(t) ⇔ ∃ c ∈ P(t): no active constraint applies to c
A(t)        = { X ∈ {AMP, CC, PACE, FC_CONN, FC_STREAM, STREAM_LIMIT} : X_ACTIVE(t) }
If SENDABLE(t) holds, no constraint is active for that content, and no packet is emitted for at least θ, the cause is a sender-implementation limit (§4.7).
4. Diagnosis classes
The diagnosis output for an interval is the set of active constraints with time-shares (§4.9), not a single label. Single labels are derived from it by an explicit rule.
4.1 CONGESTION_CONTROL_LIMITED
Congestion-control or recovery state prevents the sender from transmitting pending congestion-controlled data.
• Predicate: CC_ACTIVE(t).
• Required evidence: (1) pending data exists; (2) bif, cwnd, and packet size sufficient to evaluate bif + size > cwnd; (3) the blocked packet is not a probe-exempt packet.
• Co-activity: may coexist with FC constraints on different content. When CC and FC are both active, report both.
• Supporting signals: cwnd, bif, CC state, loss_declared, congestion_event, ACK progress, retransmission activity.
• Throughput alone is insufficient.
• TCP realization: cwnd vs bytes_in_flight/packets-out.
4.2 RECEIVER_FLOW_CONTROL_LIMITED
Receiver-granted credit prevents transmission of pending new data.
• Predicate: FC_STREAM_ACTIVE ∨ FC_CONN_ACTIVE, with scope = CONN | STREAM | BOTH.
• Required evidence: (1) NEW data pending; (2) credit values and offsets sufficient to evaluate the predicates, not merely the presence of a BLOCKED frame; (3) no stream with new data is unblocked at both levels.
• Retransmissions: pending RETX can still be sent under exhausted credit. If CC permits and RETX is pending, the sender is not stalled, but FC remains active for NEW. Record both.
• TCP realization: advertised receive window (note: relative to the ACK number, can shrink; QUIC limits are absolute and monotonic).
• QUIC realization: MAX_DATA, MAX_STREAM_DATA, and blocked conditions.
4.3 STREAM_CONCURRENCY_LIMITED
The sender cannot open streams because of MAX_STREAMS. QUIC-only; no TCP realization.
• Predicate: STREAM_LIMIT_ACTIVE.
• Required evidence: the unsatisfied open request and max_streams_k.
4.4 PACING_LIMITED
Pending data, cwnd room, and credit exist, but the pacer defers transmission.
• Predicate: PACE_ACTIVE(t).
• Required evidence: pacer wait events with next-send-time; CC_ROOM true.
• TCP realization: TCP internal pacing or fq; Linux exposes pacing_rate in tcp_info.
• Scope note: a pacing wait of one inter-packet gap is normal and is filtered by θ. Pacing-limited should indicate pacing is the gating resource over an interval, not that pacing exists.
4.5 AMPLIFICATION_LIMITED
A server before address validation has hit the 3× cap.
• Predicate: AMP_ACTIVE(t); server role only.
• Required evidence: bytes_sent, bytes_received (datagram-level), addr_validated.
• TCP realization: none.
4.6 APPLICATION_LIMITED
The transport has sending opportunity, no constraint is active, and the application has supplied nothing.
• Predicate: flow_active ∧ CC_ROOM ∧ PACE_ROOM ∧ AMP_ROOM ∧ P(t) = ∅.
• Required evidence: (1) capacity evidence for all three ROOM predicates; (2) no pending content of any class, including blocked NEW data, RETX, and CTRL; (3) flow_active.
• Boundary definition: 'application data unavailable' is evaluated at the transport-visible boundary. If a stack-level send buffer is full and the application is blocked writing to it, data is unavailable to the transport but the cause is not the application: classify as SENDER_IMPLEMENTATION_LIMITED(SEND_BUFFER).
• An idle connection is not automatically application-limited: it may be pre-handshake, closing, or finished sending.
4.7 SENDER_IMPLEMENTATION_LIMITED
Content is sendable and no protocol constraint is active, but no packet is emitted for at least θ.
• Predicate: A(t) = ∅ ∧ SENDABLE(t) ∧ idle_tx ≥ θ.
• Sub-reasons: SCHEDULER | SOCKET_BACKPRESSURE | BATCHING_GSO | CPU | TIMER_GRANULARITY | SEND_BUFFER | UNSPECIFIED.
• TCP realization: sndbuf_limited and CPU-bound sending (Linux tcp_info: tcpi_sndbuf_limited, tcpi_busy_time).
• This class is a residual defined by the absence of other constraints, so its correctness depends on the completeness of the other predicates. Report it with that caveat.
4.8 UNKNOWN
Evidence is insufficient or contradictory. Never force a label.
• Required field: reason = MISSING_SIGNAL(<signal list>) | CONFLICTING_EVIDENCE | UNVALIDATED_HOOK | PHASE_NOT_SUPPORTED.
• Accuracy reporting should give correct / wrong / UNKNOWN separately.
4.9 Interval output and single-label derivation
diagnosis(interval) = {
  active_set_shares: { CC: 0.62, FC_CONN: 0.00, PACE: 0.05, ... },
  sole_active_share: share of interval in which |A(t)| = 1, per class,
  cobinding_share:   share of interval in which |A(t)| > 1,
  primary:           class | MIXED | UNKNOWN,
  evidence_sources:  per class
}
• primary = the class with the largest time-share if that share ≥ τ (default 0.5); otherwise MIXED.
• Where |A(t)| > 1, ties are broken by a convention precedence: AMP > CC > PACE > FC_CONN > FC_STREAM > STREAM_LIMIT. This ordering is a QUICScope choice for reproducibility, not defined by any RFC. Report accuracy under alternative orderings.
• IMPL_LIMITED and APPLICATION_LIMITED are non-constraint classes: they apply only when A(t) = ∅.
5. Semantic signals
Every signal definition states its anchor (the exact point at which the signal is considered true). A hook is valid only if it implements the anchor.
5.1 pkt_sent
A QUIC packet has reached the anchor point at which QUICScope considers it transmitted.
• Anchors (record which): COMMITTED (equivalent of RFC 9002 OnPacketSent: added to the sent-packet list, bif updated) or EGRESS (the send syscall succeeded or the NIC accepted it). With pacing offload and GSO these differ.
• Unit: per QUIC packet, not per UDP datagram. One datagram can coalesce packets (e.g., Initial + Handshake).
• Fields: pn_space, pn, size, ack_eliciting, in_flight, probe, datagram_id.
• Traps: packet construction is not transmission; prepared, queued, or aborted packets must not count.
5.2 ack_received and ack_processed
• ack_received: a packet containing an ACK arrived. Fields: pn_space, largest_acked, ack_ranges, ecn_counts.
• ack_processed: the sender has finished updating its state: RTT update, newly-acked detection, loss detection, congestion-controller update, and PTO timer reset (RFC 9002 §5, §6, §7).
• Anchor: after the post-update state is consistent; emit after the CC update, not on entry.
• Fields: newly_acked_count, newly_acked_bytes, rtt_sample_taken, ecn_ce_delta, loss_detection_ran.
• An ACK that acknowledges nothing new is still recorded; it is diagnostic.
• Do not equate ack_received with ack_processed unless the selected semantics explicitly define it that way.
5.3 loss_declared
A previously outstanding packet transitions to lost under RFC 9002 §6.1 semantics.
• Reasons (record which): PACKET_THRESHOLD (kPacketThreshold = 3) or TIME_THRESHOLD (kTimeThreshold = 9/8 × max(smoothed_rtt, latest_rtt), floored at kGranularity).
• Fields: pn_space, pn, size, reason, in_flight.
• Not loss declarations:
    ◦ PTO expiry. It triggers probes only (RFC 9002 §6.2).
    ◦ Packets removed because their packet-number-space keys were discarded (RFC 9002 §6.4: removed from in-flight without a loss declaration).
• A function whose name contains 'loss' is not automatically the correct probe location.
• Spurious loss (§5.4) must be recordable against a prior loss_declared.
5.4 spurious_loss_detected
An acknowledgment arrives for a packet already declared lost. Fields: pn, time_since_declared. Affects interpretation of CC state.
5.5 pto_fired
PTO timer expiry. Fields: pn_space, pto_count, probe_packets_sent. Separate from loss_declared.
5.6 packet_discarded_no_loss
Packets removed from bif by key discard or similar, without loss declaration. Fields: pn_space, bytes_removed.
5.7 congestion_event and persistent_congestion
• congestion_event: cause = LOSS | ECN_CE; fields: cwnd_before, cwnd_after, recovery_start_time.
• persistent_congestion: loss span exceeds the persistent congestion duration, (smoothed_rtt + max(4 × rttvar, kGranularity) + max_ack_delay) × kPersistentCongestionThreshold (RFC 9002 §7.6; requires an RTT sample); cwnd collapses to the minimum.
5.8 cc_state
Snapshot or change events for cwnd, ssthresh, bif, cc_state, cc_gate. Needed to evaluate CC_ROOM.
5.9 fc_blocked
The sender has pending new data that cannot be transmitted because applicable receiver-granted credit is exhausted.
• Form: state with enter/exit events. Fields: scope = CONN | STREAM | STREAM_COUNT, stream_id (when STREAM), limit, sent_off, pending_bytes.
• Distinguish actual blocking from merely checking a limit. A hook on a limit check fires on every send and is not a blocking signal.
• Distinguish from BLOCKED frames: DATA_BLOCKED, STREAM_DATA_BLOCKED, and STREAMS_BLOCKED are optional (RFC 9000 uses SHOULD) and sent once per limit value. Their presence is strong evidence of blocking; their absence is not evidence of non-blocking. Library 'newly blocked' helpers are often edge-triggered to decide when to emit these frames and are poor fc_blocked hooks.
• Separate signals: blocked_frame_sent, blocked_frame_received, max_data_received, max_stream_data_received, max_streams_received (each with the new limit).
5.10 pacing_wait and amp_state
• pacing_wait: enter/exit; next_send_time, pacing_mode.
• amp_state: enter/exit; bytes_sent, bytes_received, addr_validated.
5.11 app_limited
The transport has additional sending opportunity, but no application data exists to use it (§4.6).
• Two variants, tagged explicitly:
    ◦ app_limited_state (instantaneous): the §4.6 predicate holds now.
    ◦ app_limited_sample_mark (sticky): a per-sample mark, as in the delivery-rate estimation draft used by BBR (draft-cheng-iccrg-delivery-rate-estimation), set for packets sent while app-limited and cleared when the marked data has been acknowledged.
• RFC 9002 §7.8 and its pseudocode treat 'app or flow-control limited' as one condition for not growing cwnd. QUICScope separates them. State this difference when comparing with stack CC behavior.
• An idle connection is not automatically app-limited (see §1 flow-active).
5.12 stream_open_blocked
Enter/exit for an unsatisfied stream open. Fields: stream_type, requested_index, max_streams.
6. Evidence types
Every recorded signal carries a source:
• WIRE_DIRECT: the signal is a literal field or frame observable on the wire given the stated vantage and decryption status.
• WIRE_INFERRED: derived from wire observations by a named inference rule.
• ENDPOINT: emitted by an endpoint hook or the endpoint's own log (including stack-native qlog).
• CONTROLLED_GROUND_TRUTH: set by experiment control rather than observed (configured link rate and delay, injected loss pattern, configured MAX_DATA/MAX_STREAM_DATA, application write schedule, configured pacing).
6.1 Required attributes beyond source
Attribute
Values / meaning
vantage
SENDER_ENDPOINT, RECEIVER_ENDPOINT, MID_PATH, SENDER_HOST_TAP
decryption
NONE, KEYLOG (e.g., SSLKEYLOGFILE), ENDPOINT_PLAINTEXT
visibility_layer
UDP_IP, QUIC_HEADER (invariants, spin bit, cleartext fields), QUIC_PN (packet number after header-protection removal), QUIC_FRAME (payload frames)
inference_rule
Required when source = WIRE_INFERRED: rule identifier and version
hook_validation
`UNVALIDATED
clock_domain
Clock identity and estimated error bound; needed to order sender and receiver events
anchor
Where applicable (e.g., `COMMITTED
stack, stack_version, quic_version
Implementation identity (e.g., quic-go, MsQuic, ngtcp2, picoquic)
6.2 Feasibility of WIRE_DIRECT
For QUIC, packet numbers are header-protected, and ACK, MAX_DATA, MAX_STREAM_DATA, and *_BLOCKED frames are inside the encrypted payload (RFC 9001, RFC 9312). Without keys a passive observer sees little beyond UDP/IP headers, QUIC header invariants, and the spin bit. WIRE_DIRECT for QUIC frame-level signals therefore requires decryption ≠ NONE.
Signal
TCP (wire)
QUIC, no keys
QUIC, keys at wire
Notes
datagram sent
WIRE_DIRECT
WIRE_DIRECT (UDP)
WIRE_DIRECT
Sender-side tap sees host egress, not necessarily network egress
pkt_sent per QUIC packet
WIRE_DIRECT (segment)
not available
WIRE_DIRECT
Coalescing needs per-packet parsing
ack_received
WIRE_DIRECT
not available
WIRE_DIRECT at sender vantage
Receipt only
ack_processed
ENDPOINT
ENDPOINT
ENDPOINT
Never wire-direct
flow-control credit
WIRE_DIRECT (window field; scale from SYN)
not available
WIRE_DIRECT (frames)

fc_blocked state
ENDPOINT or WIRE_INFERRED
ENDPOINT
ENDPOINT or WIRE_INFERRED
BLOCKED frames are evidence only
cwnd, cc_state
ENDPOINT
ENDPOINT
ENDPOINT
Never wire-direct
bif
WIRE_INFERRED
not available
WIRE_INFERRED (approximate)
Needs ACK and PN tracking
loss_declared
ENDPOINT or WIRE_INFERRED
ENDPOINT
ENDPOINT or WIRE_INFERRED
Never wire-direct: it is an endpoint decision
app_limited
ENDPOINT or WIRE_INFERRED
ENDPOINT
ENDPOINT or WIRE_INFERRED
Never wire-direct
Signals that are endpoint-internal decisions (cwnd, bif, loss_declared, app_limited, fc_blocked, pacing and amplification gates) can never be WIRE_DIRECT; the wire shows only their consequences. QUIC never reuses packet numbers (RFC 9000 §12.3), which removes TCP's retransmission ambiguity, but wire-side loss inference still requires frame-level decryption and frame matching.
7. Record schema
record = {
  timestamp, clock_domain,
  connection_id, role (client|server), phase,
  signal, event_or_state (event | enter | exit), value,
  pn_space, pn, stream_id, scope, probe,
  source, vantage, decryption, visibility_layer,
  inference_rule, hook_validation, anchor,
  implementation, stack_version, quic_version, probe_id
}
8. External mappings
Use these as cross-checks against QUICScope's own probes. Names are from recall; verify against current documents.
QUICScope
RFC 9002 pseudocode (appendices A, B)
qlog event
TCP
pkt_sent
OnPacketSent
packet_sent
segment egress
ack_received
entry of OnAckReceived
packet_received (ACK frame)
ACK ingress
ack_processed
end of OnAckReceived
metrics_updated (follow-on)
tcp_ack processing
loss_declared
DetectAndRemoveLostPackets
packet_lost
retransmit / RACK mark
pto_fired
OnLossDetectionTimeout
loss_timer_updated
RTO / TLP
cc_state
OnPacketsAcked, OnCongestionEvent
metrics_updated, congestion_state_updated
tcp_info cwnd, ssthresh
app_limited
IsAppOrFlowControlLimited (combined)
(none)
tcpi_busy_time and SndLimTime split
fc_blocked
(none)
(none standard)
rwnd_limited
TCP prior art for validating the TCP side: RFC 4898 (TCP-ESTATS) defines SndLimTime split by Rwin, Cwnd, and Sender; Linux tcp_info exposes tcpi_rwnd_limited, tcpi_sndbuf_limited, and tcpi_busy_time; Dapper partitions TCP performance problems by sender, network, and receiver.
9. Hook validation obligations
A hook is not usable as evidence until validated:
• pkt_sent: per-packet count and size match a decrypted wire capture at the sender vantage within a stated tolerance; prepared or aborted packets excluded.
• ack_processed: fires after CC update; emitted exactly once per ACK frame.
• loss_declared: matches injected drops under controlled loss; no emission on PTO expiry or key discard.
• fc_blocked: matches controlled MAX_DATA / MAX_STREAM_DATA exhaustion experiments; fires on enter/exit, not on each limit check; independent of BLOCKED frame emission.
• cc_state: bif reconstructed from pkt_sent, ack_processed, loss_declared, and packet_discarded_no_loss equals the hook's bif within tolerance.
• app_limited: matches the controlled application write schedule.
• Each stack's probe records the validation method and reference in hook_validation.
10. Open design decisions
1. θ and τ defaults and their sensitivity.
2. Precedence ordering for single-label scoring and robustness to alternatives.
3. Instantaneous vs sticky app_limited as the primary semantics.
4. cc_gate strict vs lax normalization across stacks.
5. Whether IMPL_LIMITED sub-reasons are observable on all four stacks or only some.
6. Whether to define a min-cut refinement: a constraint is critical when relaxing it alone would allow transmission, which separates sole bottlenecks from co-bound ones.
