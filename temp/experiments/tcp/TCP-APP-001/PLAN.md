# TCP-APP-001 – Controlled Non‑Backlogged / Application‑Limited TCP Sender

**Purpose** – Design an experiment that deliberately creates periods in which the
TCP sender **may** have no pending data at the transport send boundary (i.e.
`HasTransportPendingData` could become **false**) while the receiver’s flow‑
control window and the sender’s congestion‑control algorithm would otherwise
allow additional data.  The aim is to collect passive‑observer evidence that can
support an `APPLICATION_LIMITED` inference in the QUICScope state machine.

---

## 1. Semantic Target

| Predicate | Desired value |
|-----------|----------------|
| **D** – `HasTransportPendingData` | **false** |
| **F** – `FlowControlAllowsNewData` | **true** |
| **C** – `CongestionControlAllowsNewData` | **true** |

When the three predicates hold simultaneously the state machine defines the
`APPLICATION_LIMITED` branch.

*Important definition*: `D` means that **application payload has already been
submitted to the transport and remains unsent / queued at the transport send
boundary**.  It does **not** refer to data that is still owned or buffered by
the application before the `send()` call.  Consequently `D = false` can only be
asserted after any previously submitted data has fully drained from the send
queue.

---

## 2. Experimental Question

> *When the sender is deliberately non‑backlogged, what evidence is visible to a
> passive TCP observer, and can that evidence support an `APPLICATION_LIMITED`
> inference?*

The experiment must provide a **CONTROLLED_WORKLOAD_TIMELINE** – timestamps of
when the application invokes `send()` and when intentional sleeps occur – and it
must capture the full TCP trace on the sender side.  The analysis will compare
the two to assess how reliably a passive observer can infer periods during
which the transport has no pending data (i.e. `D` may be *false*), without
mistaking ordinary network gaps for intentional non‑backlogged behavior.

---

## 3. Testbed (identical to TCP‑BASE‑001)

| VM | Hostname | Interface | IP address | Role |
|----|----------|-----------|------------|------|
| **VM1** | `sriov-vm1` | `ens4` | `192.168.88.20/24` | Sender **+** passive observer |
| **VM2** | `sriov-vm2` | `ens4` | `192.168.88.21/24` | Receiver |

The management interface `ens3` is **never** used for experiment traffic.

*No changes* are proposed to MTU, NIC offloads, congestion‑control algorithm,
`sysctl` settings, qdisc, or NIC configuration.  No network emulation (`netem`
is required.

---

## 4. Workload Design (sender & receiver)

### 4.1 Sender behavior (pseudo‑code)

```python
import socket, time, os, struct

SERVER = "192.168.88.21"
PORT   = 5202               # dedicated port for this experiment (different from any iperf3 baseline)
CHUNK  = 64 * 1024          # 64 KiB application write size
PAUSE  = 0.100              # 100 ms intentional idle interval
REPS   = 20                 # number of bursts

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((SERVER, PORT))
# Record wall‑clock timestamps that can be aligned with tcpdump (nanoseconds since epoch)
log_event("conn_established", time.time_ns())

payload = b"x" * CHUNK
for i in range(REPS):
    log_event("pre_send", time.time_ns(), i)
    sent = sock.send(payload)          # may be less than CHUNK; record the actual bytes accepted
    log_event("post_send", time.time_ns(), i, sent)
    log_event("app_sleep_start", time.time_ns(), i)
    time.sleep(PAUSE)
    log_event("app_sleep_end", time.time_ns(), i)

log_event("close_start", time.time_ns())
sock.shutdown(socket.SHUT_WR)
sock.close()
log_event("close_end", time.time_ns())
```

*Rationale for parameters*:
*Rationale for parameters*:
* **Chunk size 64 KiB** – an application‑level write that will be segmented into many TCP segments (MSS ≈ 1460 bytes) and is large enough to produce a distinguishable transmission burst.
* **Pause 100 ms** – deliberately longer than the RTT on the local SR‑IOV 
* **Pause 100 ms** – deliberately longer than the RTT on the local SR‑IOV testbed,
  creating an idle gap that is easily observable in the packet trace.
* **Repetitions = 20** – yields a statistically meaningful number of bursts
  while keeping the total runtime modest.

After the first execution we will verify that the capture shows:
* distinct bursts of data packets separated by **no packets** lasting roughly the
  pause duration,
* cumulative ACKs that advance monotonically during each burst and remain idle
  during the pause.
If the gaps are shorter than expected, the pause can be increased before the
final runs.

### 4.2 Receiver behavior (pseudo‑code)

```python
import socket, os

LISTEN = "0.0.0.0"
PORT   = 5202

svr = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
svr.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
svr.bind((LISTEN, PORT))
svr.listen(1)
conn, addr = svr.accept()
log_event("conn_accepted", time.time_ns(), addr)

while True:
    data = conn.recv(64 * 1024)   # read as fast as possible
    if not data:
        break
    # Data is discarded; no artificial back‑pressure is applied.
log_event("conn_closed", time.time_ns())
conn.close()
svr.close()
```

The receiver reads with a large buffer and does **not** impose any artificial
receive‑window limitation; it simply advertises the default receive window
adjusted by the kernel.

---

## 5. Controlled Workload Timeline (log)

The sender will write a **controlled workload timeline** (`controlled_workload_timeline.log`)
in plain‑text CSV format.  The log records wall‑clock timestamps (nanoseconds since
the Unix epoch) produced by `time.time_ns()` so that they can be aligned with the
timestamps produced by `tcpdump` on the same host.

```
# event, ts_ns, iteration(optional), bytes_requested(optional), bytes_accepted(optional)
conn_established, 1700000000000000000,
pre_send, 1700000000100000000,0
post_send, 1700000000120000000,0,65536
app_sleep_start, 1700000000120000000,0
app_sleep_end, 1700000001220000000,0
pre_send, 1700000001320000000,1
post_send, 1700000001340000000,1,65536
app_sleep_start, 1700000001340000000,1
... (repeated for each iteration) ...
close_start, 1700000005000000000,
close_end, 1700000005020000000,
```

**What is NOT claimed**: These timestamps record *when* the application calls
`send()` and when it sleeps, but they do **not** constitute exact ground‑truth
for the `D` predicate.  `D = false` can only be asserted after the transport’s
send queue has fully drained, which may occur sometime after an `app_sleep_start`
event.

### 5.1 Optional endpoint observation for exact `D`

Obtaining precise `D` timestamps requires endpoint observation that can measure
the amount of unsent/queued transport data (for example, by instrumenting the
kernel’s TCP stack or using a suitable eBPF probe).  The details of such
instrumentation are left for future work and are classified as **ENDPOINT**
data.

---

## 6. Passive Capture

*Tool*: `tcpdump`

*Interface*: `ens4` on VM1 (sender / observer)

*Capture start*: `tcpdump` is started **before** the sender initiates the
connection, ensuring that the TCP three‑way handshake is captured.

*Filter*: The experiment uses a dedicated server port (`5202`).  The capture can
use a static filter that includes all traffic between the two hosts on that
port; the exact 4‑tuple will be identified later from the trace.

```bash
RUN_DIR="/home/rosa/experiments/tcp/TCP-APP-001/run-001"
mkdir -p "$RUN_DIR"
PCAP="$RUN_DIR/tcp_capture.pcap"
STAT="$RUN_DIR/capture_stats.txt"
sudo tcpdump -i ens4 -s 256 -w "$PCAP" \
    "tcp and host 192.168.88.20 and host 192.168.88.21 and port 5202" \
    -nn -tttt 2> "$STAT" &
echo $! > "$RUN_DIR/tcpdump.pid"
```

*Snaplen*: `256` bytes – sufficient to retain the full Ethernet, IP, and TCP
headers plus all TCP options (MSS, SACK, timestamps, window‑scale).  Payload
bytes are not needed for the inference.

*Output*: `tcp_capture.pcap` plus `capture_stats.txt` (stderr from `tcpdump`).

---

## 7. Passive Observer Evidence (what to extract from the pcap)

| Evidence | Extraction method (example) | Evidence level |
|----------|-----------------------------|----------------|
| **Data bursts** (clusters of data packets) | Identify runs of successive packets with payload length > 0 and inter‑packet gaps < few ms. | **WIRE_DERIVED** |
| **Idle gaps** between bursts | Measure time between the last data packet of a burst and the first data packet of the next burst. | **WIRE_DERIVED** |
| **Sequence‑number progression** | Plot `seq` values of data packets; should increase monotonically within a burst. | **WIRE_DIRECT** |
| **Cumulative ACK progression** | Extract `ack` numbers from pure‑ACK packets; should advance during bursts and stay flat during pauses. | **WIRE_DIRECT** |
| **Receiver advertised window** | Read raw `win` field from ACKs; track its value (scaled later). | **WIRE_DIRECT** |
| **Scaled advertised window** | Apply negotiated window‑scale (derived from SYN/SYN‑ACK) to `win`. | **WIRE_DERIVED** |
| **Outstanding‑data estimate** | Use the high‑water mark of sender `seq` minus the latest cumulative `ack` (per‑direction, per‑flow). | **WIRE_DERIVED** |
| **Retransmission / loss indications** | Duplicate `seq` numbers, SACK blocks, or TCP‑Reno fast‑retransmit patterns. | **WIRE_INFERRED** (requires heuristic of “duplicate‑seq = loss”) |

The observer will thus have a timeline of *active* data transmission periods and
*idle* periods that correspond to the intentional workload pauses.

---

## 8. Application‑Limited Inference (passive view)

1. **Controlled workload behavior** – The sender deliberately inserts a 100 ms
   idle interval after each 64 KiB write.  During the idle interval the
   application does *not* call `send()`.  Whether the transport queue is empty
   (`D = false`) depends on how quickly the previously submitted burst drains.
2. **Endpoint ground truth** – The `controlled_workload_timeline.log` provides
   exact timestamps of application‑level events but does **not** directly reveal
   the moment when the transport’s pending data becomes empty.
3. **Passive wire observations** – From the pcap the observer can extract the
   timestamps of the last data packet of a burst and the first data packet of
   the subsequent burst (idle gaps).  These gaps, together with the lack of
   congestion signals and a sufficiently large advertised receiver window, form
   the evidence that a passive system may use to *infer* that the sender was
   not back‑logged.
4. **Inference classification** – Any inference that `D = false` based solely
   on an observed idle gap is a **WIRE_INFERRED** conclusion; it is not a direct
   measurement.  The experiment will collect the data first; a concrete
   classification rule (e.g., a threshold on gap duration) will be derived
   during later analysis.

*We do not claim* that low throughput or the mere absence of packets proves
`APPLICATION_LIMITED`.  The inference relies on the observed burst/idle pattern
and on the observation that flow‑control (`F`) and congestion‑control (`C`)
are **not intentionally constrained** – see Section 6 for the evidence to be
checked.

---

## 9. Validation Methodology

For each of the **20 intentional pauses** we will compare four timelines:

1. **Controlled workload pause** – interval `[app_sleep_start, app_sleep_end]`
   from `controlled_workload_timeline.log`.
2. **Endpoint D ground truth** – if future endpoint instrumentation is added,
   its timestamps would be recorded as `D_false_start` / `D_false_end`
   (**ENDPOINT_GROUND_TRUTH**).
3. **Passive observer idle gap** – interval `[last_data_pkt_ts, next_data_pkt_ts]`
   measured from the pcap.
4. **Observer inference** – a binary decision per gap (e.g., *gap detected* →
   *possible `D = false`*).  The exact rule for converting a gap into an
   inference will be defined after the data are collected.

**Candidate metrics** (to be computed after the run, not now):
* Number of intentional non‑backlogged intervals (should be 20).
* True positives – passive observer correctly identifies an interval where the
  transport queue has drained.
* False positives – observer infers `D = false` while the transport still holds
  pending data.
* False negatives – observer fails to detect an interval in which the transport
  queue is empty.
* Detection delay – time between `app_sleep_start` and the beginning of the
  observed idle gap.

---

## 10. Expected Artifacts

```
experiments/tcp/TCP-APP-001/
├─ PLAN.md                     # (this file)
├─ sender.py                   # placeholder for the sender implementation
├─ receiver.py                 # placeholder for the receiver implementation
└─ run-001/
   ├─ sender.log               # stdout/stderr of the sender process
   ├─ receiver.log             # stdout/stderr of the receiver process
   ├─ controlled_workload_timeline.log # CSV log described in §5
   ├─ environment.txt          # system metadata (date, kernel, etc.)
   ├─ tcp_capture.pcap         # raw passive capture (snaplen 256)
   ├─ capture_stats.txt        # tcpdump stderr / statistics
   └─ RESULTS.md               # to be filled after the run
```

The sender script is now implemented. Run it with an explicit timeline path, for example:

```bash
python3 /home/rosa/experiments/tcp/TCP-APP-001/sender.py \
    --timeline /home/rosa/experiments/tcp/TCP-APP-001/run-001/controlled_workload_timeline.log
```

The receiver script remains unchanged.

---

## 11. Relation to the QUICScope State Machine

**Semantic state under test**

```
APPLICATION_LIMITED
```

**Target predicate combination**

```
D = false
F = true
C = true
```

**Evidence question**

> *Can passive TCP evidence distinguish `D = false` from `D = true` while
> ruling out receiver‑flow‑control and congestion‑control limitation strongly
> enough to support the `APPLICATION_LIMITED` diagnosis?*

The experiment validates the **passive‑observer branch** of the state machine:
it provides the minimal observable cues (burst/idle pattern, window
advertisements, lack of loss) that a passive system could use to infer the
`APPLICATION_LIMITED` node.  Subsequent experiments (e.g., TCP‑FC‑001) will
exercise the other branches.

---

*End of PLAN.md.*
