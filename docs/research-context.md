# QUICScope Research Context

## Research Problem

Network diagnosis requires explaining why a connection is not making
expected progress.

A throughput measurement can establish that performance is poor, but
does not by itself identify the limiting component.

Relevant causes include:

- packet loss and recovery;
- congestion-control limitation;
- receiver flow-control limitation;
- application-limited sending.

QUIC makes this problem particularly interesting because many transport
semantics that were traditionally available to TCP packet analysis are
not exposed through the same passive wire interface.

## TCP Baseline

TCP provides a useful comparison because important transport information
appears directly in TCP headers.

Examples include:

- sequence numbers;
- acknowledgments;
- advertised receive window;
- TCP flags;
- SACK information.

Packet traces can therefore provide evidence about sender progress,
receiver progress, retransmission/recovery behavior, and receiver
backpressure.

However, not every TCP transport state is directly encoded in a header.

For example, sender congestion-window state is endpoint state.

Therefore the TCP experiments must distinguish between:

1. direct wire evidence;
2. inference from wire evidence;
3. endpoint evidence.

## QUIC

QUIC preserves many of the same high-level transport responsibilities:

- acknowledgments;
- loss detection;
- congestion control;
- flow control;
- stream delivery.

However, QUIC protects most transport information cryptographically.

This changes the diagnosis surface.

Some causal decisions are naturally endpoint-side events, including
whether:

- an outstanding packet was declared lost;
- congestion control prevented transmission;
- flow-control credit prevented transmission;
- the application had data available.

## QUICScope

QUICScope aims to recover a small set of transport-semantic signals from
heterogeneous QUIC implementations.

The semantic signal definition should remain stable even when its
implementation changes.

For example:

    semantic event:
        loss_declared

may map to different functions, structures, or code paths in:

- quic-go;
- MsQuic;
- ngtcp2;
- picoquic.

Therefore QUICScope separates:

    WHAT happened at the protocol-semantic level

from:

    WHERE that event appears in a particular implementation.

## Probe Discovery

The coding agent receives:

- semantic signal definition;
- relevant RFC context;
- target implementation source;
- symbol/source information.

It proposes candidate locations where the event might become observable.

These are hypotheses.

## Validation

QUICScope instruments candidate locations and compares their runtime
behavior against independent evidence.

Only validated probes become part of the shared semantic signal
interface.

## Long-Term Goal

The desired abstraction is:

    heterogeneous transport implementation
                    ↓
          stack-specific probes
                    ↓
        shared semantic signals
                    ↓
             diagnosis logic
                    ↓
      diagnosis + supporting evidence
