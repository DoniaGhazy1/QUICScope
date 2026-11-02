## Current Research Phase

The current research goal is to determine what transport information is
needed to diagnose why a connection is not making expected progress,
where that information can be observed in TCP, and how the same
diagnostic semantics can be recovered for QUIC.

The work proceeds from transport semantics rather than from a particular
implementation or measurement tool.

### 1. Define the diagnostic states

Construct explicit semantic state machines for the transport behaviors
needed to distinguish the target diagnosis cases:

- congestion-control-limited;
- receiver-flow-control-limited;
- application-limited;
- loss/recovery behavior where it affects diagnosis.

For each state and transition, define:

- the semantic meaning of the state;
- the conditions required to enter it;
- the conditions required to leave it;
- the transport variables/events needed to identify it;
- which observations are necessary versus merely supporting evidence.

The state machine must be defined independently of TCP or QUIC
implementation-specific function names.

### 2. Determine what TCP exposes on the wire

Use TCP as the reference case for understanding how much of the
diagnostic state can be reconstructed from network traffic.

For each required semantic signal, determine whether TCP provides it as:

- directly wire-visible;
- inferable from wire observations;
- endpoint-only.

Relevant TCP wire observations may include:

- sequence numbers;
- acknowledgment numbers;
- TCP flags;
- advertised receive window;
- SACK information;
- TCP options;
- packet timing;
- payload length;
- retransmission patterns.

Do not assume that every diagnostic state is directly encoded in a TCP
header.

For example, congestion window is endpoint state rather than a TCP
header field. If a semantic state requires information that cannot be
directly observed, determine whether it can be inferred from the packet
trace and document the assumptions required for that inference.

### 3. Experimentally validate TCP diagnosis

Construct controlled experiments that intentionally produce the target
conditions.

For each experiment compare:

    controlled ground truth
            ↓
    TCP wire observations
            ↓
    TCP endpoint observations
            ↓
    reconstructed semantic state

The goal is to determine exactly which diagnosis claims can be made
from the TCP wire alone and which require endpoint information.

### 4. Map the same semantic requirements to QUIC

Once the required diagnostic signals are understood, evaluate the same
semantic requirements for QUIC.

Do not create a completely different diagnosis model for QUIC.

The diagnostic question should remain the same:

    Why is this connection unable to make additional progress?

The semantic states should remain transport-level concepts.

What changes is the observability of the evidence needed to identify
those states.

For every signal required by the semantic state machine, determine
whether QUIC makes it:

- directly wire-visible;
- available after packet decryption;
- inferable from wire behavior;
- endpoint-only.

### 5. Identify the QUIC observability gap

Construct an explicit mapping:

    diagnostic state
        ↓
    required semantic signals
        ↓
    TCP observability
        ↓
    QUIC observability
        ↓
    missing evidence

The missing evidence defines the endpoint signals that QUICScope needs
to recover.

Do not begin with arbitrary implementation variables and ask whether
they are useful.

Begin with the semantic state machine and derive the minimum evidence
required to distinguish its states.

### 6. Recover missing QUIC signals from the endpoint

For signals that cannot be reliably obtained from the QUIC wire,
QUICScope should recover the corresponding semantic event/state from
the running endpoint.

The workflow is:

    semantic requirement
            ↓
    RFC-level definition
            ↓
    target QUIC implementation
            ↓
    candidate implementation locations
            ↓
    eBPF probe
            ↓
    runtime validation
            ↓
    normalized semantic signal

The coding agent may propose candidate extraction locations, but a
candidate is not considered correct until it has been independently
validated.

### Current Immediate Task

The immediate task is therefore NOT simply "run TCP experiments."

It is:

1. define the semantic state machine needed for diagnosis;
2. identify the minimum signals required to distinguish its states;
3. determine which of those signals can be recovered from TCP packets;
4. experimentally validate those TCP observations;
5. determine which equivalent evidence is unavailable from QUIC;
6. recover the missing QUIC evidence using endpoint instrumentation.

The desired final mapping is:

    controlled transport condition
                ↓
       semantic ground truth
                ↓
        required signals
          ↙           ↘
    TCP wire       TCP endpoint
          ↓
    TCP diagnosis
          ↓
    same semantic requirements
          ↓
       QUIC wire
          ↓
     missing signals
          ↓
    QUIC endpoint probes
          ↓
      QUIC diagnosis
