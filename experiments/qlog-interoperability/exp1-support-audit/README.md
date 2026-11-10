
# Experiment 1 — Cross-Implementation qlog Support Audit

## 1. Objective

This experiment investigates the availability and behavior of native qlog instrumentation across three QUIC implementations:

- **quic-go**
- **picoquic**
- **ngtcp2**

The goal is to determine which standardized qlog events and fields are implemented and emitted by each stack, and whether the resulting traces provide sufficient information for transport-level performance diagnosis.

This is part of the QUICScope research project, which investigates the observability of QUIC transport behavior across heterogeneous implementations.

The experiment distinguishes three questions:

1. **Source-level support:** Does an implementation contain code capable of emitting a particular qlog event or field?
2. **Runtime emission:** Is the event or field actually recorded under a controlled workload?
3. **Diagnostic usefulness:** Is the emitted information sufficient to characterize the transport behavior being investigated?

An event that does not appear in a trace is not automatically considered unsupported. The workload may not have triggered the corresponding condition.

## 2. Implementations and Environment

| Component | Version / configuration |
|---|---|
| quic-go | Pinned commit `ed90516797ec8ed7314c2b163797eca58fd5a2b8` |
| picoquic | Pinned commit `77fa50201a2897a1aa90f9d0ff43e8d2fd39d182` |
| ngtcp2 | Pinned commit `e82176c8105490eeedb1ee1c805578d9ea867672` |
| ngtcp2 TLS backend | GnuTLS 3.8.3 |
| ngtcp2 compiler | GCC 14, C++23 |
| nghttp3 | 1.18.0, locally built |
| quic-go compiler | Go 1.26.0 |
| Host | Linux VM, Ubuntu 24.04, x86-64 |
| Network | Localhost / loopback |

The three implementations use their native qlog facilities. No common qlog instrumentation layer is inserted between the implementations and their transport logic.

**Source provenance caveat:** The quic-go checkout contains earlier experimental modifications associated with loss-recorder work. Its exact working-tree state and the relationship between those changes and qlog behavior must be recorded and reviewed before the final dataset is collected.

## 3. Common Workload — EXP1-B0

The baseline workload is a single HTTP/3 file download over QUIC.

| Parameter | Value |
|---|---|
| Application protocol | HTTP/3 |
| QUIC version | QUIC v1, observed in the quic-go/picoquic setup and to be confirmed across final runs |
| Request | `GET /payload.bin` |
| Transfer direction | Server → Client |
| Number of connections | One per validation run |
| Number of file requests | One |
| Payload size | 1,048,576 bytes (1 MiB) |
| Payload type | Deterministic pseudorandom binary data |
| Random generator | Python `random.Random(20261110)` |
| Network topology | Client and server on the same VM |
| Network interface | Loopback (`127.0.0.1`) |
| Artificial delay/loss | None intentionally configured for this baseline; actual qdisc configuration to be recorded |
| TLS | TLS 1.3 using local test certificates |
| Native qlog | Enabled on client and server |
| Correctness check | Downloaded payload compared byte-for-byte against reference file |

### Reference payload

The input file is located at:

`fixtures/payload.bin`

It was generated with:

```python
import random
from pathlib import Path

rng = random.Random(20261110)
data = rng.randbytes(1024 * 1024)
Path("fixtures/payload.bin").write_bytes(data)
```

Expected SHA-256:

```text
9bf9f0415bf644a419988c10cfa2e6bd089a16a207feef0f8420e66ebedf17f8
```

This file is shared across all three implementations.

Using identical content allows us to verify that the application payload is consistent. It does not guarantee identical transport packetization, congestion-control decisions, ACK behavior, or HTTP/3 framing.

## 4. Native qlog Configuration

| Implementation | Logging mechanism |
|---|---|
| quic-go | HTTP/3 `qlog.DefaultConnectionTracer`, configured through `QLOGDIR` |
| picoquic | Native `-q <directory>` option |
| ngtcp2 | Native `--qlog-dir=<directory>` option |

Both client-side and server-side traces are collected.

quic-go and ngtcp2 produce `.sqlog` traces in the observed runs. Picoquic produces `.qlog` files.

The formats and schemas must be inspected before comparing events. File sizes alone do not establish logging completeness.

## 5. Experimental Procedure

For each implementation:

1. Start an HTTP/3 server on the local VM.
2. Configure the server to serve the shared `fixtures/payload.bin`.
3. Enable native server-side qlog logging.
4. Start one HTTP/3 client and enable native client-side qlog logging.
5. Request `/payload.bin`.
6. Save the response body to an output file.
7. Verify the transfer completed successfully.
8. Verify that the output is byte-for-byte identical to the reference payload.
9. Preserve the native client/server qlogs and associated logs.
10. Record the implementation revision, runtime configuration, and environment.

The current repository includes manually executed validation runs. A reusable script, `scripts/run_baseline.sh`, is being prepared to automate this procedure and collect uniquely identified runs.

The automated runner must be validated separately before it is used for final measurements.

## 6. Validation Results — November 10, 2026

All three implementations successfully transferred the same 1 MiB reference payload and generated native client/server qlogs.

| Implementation | Payload validation | Client qlog | Server qlog |
|---|---|---:|---:|
| quic-go | PASS | 282,186 bytes | 396,293 bytes |
| picoquic — fresh-ticket validation | PASS | 307,875 bytes | 56,586 bytes |
| ngtcp2 | PASS | 331,509 bytes | 437,377 bytes |

All three downloaded files matched the reference SHA-256.

### quic-go

Successful HTTP/3 download:

- HTTP response: `200 OK`
- Download size: 1,048,576 bytes
- Client process exit status: 0
- Byte-for-byte comparison: PASS
- Both endpoints generated native qlogs

Trace files:

```text
runs/EXP1-B0/quic-go/client_qlog/c34b8b2deab8a1f6_client.sqlog
runs/EXP1-B0/quic-go/server_qlog/c34b8b2deab8a1f6_server.sqlog
```

The client reported a UDP receive-buffer-size warning. The transfer succeeded, but the warning should be documented before interpreting timing or performance measurements.

### picoquic

Successful HTTP/3 download:

- HTTP/3 ALPN: `h3`
- Download size: 1,048,576 bytes
- Client-reported exit code: 0
- Byte-for-byte comparison: PASS
- Both endpoints generated native qlogs

The initial 1 MiB validation attempted to use a previously stored TLS session ticket and reported 0-RTT activity. That run is preserved but excluded from the intended fresh-connection baseline.

A subsequent validation used a separate session-ticket file and completed successfully. The full handshake trace still needs to be inspected to confirm the absence of resumption or 0-RTT.

Fresh-run trace files:

```text
runs/EXP1-B0/picoquic-fresh/client_qlog/8c719f00ab483c21.client.qlog
runs/EXP1-B0/picoquic-fresh/server_qlog/8c719f00ab483c21.e933.server.qlog
```

The server-side qlog is substantially smaller than the client-side qlog. This observation requires event-level analysis before any conclusion about support or completeness can be drawn.

### ngtcp2

Successful HTTP/3 download:

- Download size: 1,048,576 bytes
- Client process exit status: 0
- Byte-for-byte comparison: PASS
- Both endpoints generated native qlogs

Trace files:

```text
runs/EXP1-B0/ngtcp2/client_qlog/08664079925a73b01cec19749351e90990.sqlog
runs/EXP1-B0/ngtcp2/server_qlog/66f6fea1d140b047bea457cf5224a16053e4.sqlog
```

The client log included `ngtcp2_conn_handle_expiry: ERR_IDLE_CLOSE`. This requires trace inspection before classifying the connection termination behavior.

## 7. Current Limitations

The validation results establish that all three implementations can successfully transfer the same application payload and produce native qlogs.

They do **not** yet establish that the implementations were operating under equivalent transport configurations.

The following must be verified or aligned before the final comparison:

- Congestion-control algorithm and configuration
- Initial connection-level and stream-level flow-control windows
- Initial congestion window
- ACK and delayed-ACK configuration
- QUIC version and negotiated transport parameters
- TLS session resumption and 0-RTT behavior
- UDP segmentation/offload behavior
- Socket buffer configuration
- Network qdisc and impairment state
- qlog event schemas and logging completeness
- Exact implementation source and binary provenance

Differences in implementation-specific transport behavior are expected and cannot be eliminated entirely.

The experiment therefore aims to control the common workload and document remaining implementation-level differences.

## 8. Planned qlog Analysis

After freezing the configuration and collecting clean runs, the analysis will proceed in three stages.

### Stage A — Structural validation

- Verify each qlog is parseable.
- Identify its format and declared event schemas.
- Extract event names and fields.
- Distinguish QUIC transport events from HTTP/3 events.
- Check trace metadata and endpoint roles.

### Stage B — Cross-implementation support audit

- Map observed events against the selected IETF qlog specification.
- Inspect implementation source code for corresponding event emitters.
- Distinguish implemented, observed, and not-observed events.
- Record missing, optional, and implementation-specific fields.
- Document differences in semantics and emission granularity.

### Stage C — Targeted validation

Where baseline traces do not trigger the relevant events, controlled experiments will be required.

Potential scenarios include congestion-related loss, flow-control blocking, application-limited sending, and other conditions relevant to the QUICScope diagnostic model.

Any causal or semantic conclusion must be supported by controlled triggering conditions and, where appropriate, an independent oracle.

## 9. Reproducibility and Evidence Policy

Raw native qlogs are retained in the repository alongside experiment scripts and documentation.

For final runs, each execution should have a unique directory containing:

- Native client and server qlogs
- Client and server process logs
- Workload identity and payload checksum
- Client process status and transfer verification
- Implementation source revision and working-tree status
- Build configuration and binary identity
- Relevant network configuration
- Run timestamp and unique identifier

Earlier validation traces are retained separately from final measurements.

A successful transfer is necessary but not sufficient evidence that the qlogs are semantically equivalent or complete.

**No event-support or diagnostic-coverage conclusion is made solely from qlog file size or the absence of an event in one baseline trace.**

## 10. Experiment Status

**Status: Common-workload validation completed; configuration freeze and event-support audit pending.**

Completed:

- Three QUIC implementations built and executable
- Native client/server qlog generation verified
- Shared 1 MiB fixture created
- Successful HTTP/3 download verified for each implementation
- Byte-for-byte payload comparison passed for all three

Pending:

- Validate the automated experiment runner
- Freeze and record transport parameters
- Verify fresh TLS handshake behavior
- Validate qlog structures and schemas
- Collect final repeated runs
- Perform source-level and runtime event-support comparison
- Evaluate the diagnostic usefulness of supported events

The validation results should not yet be interpreted as evidence of superior or inferior qlog implementation quality.