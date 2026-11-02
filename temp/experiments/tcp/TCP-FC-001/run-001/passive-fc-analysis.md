# Passive Flow‑Control Analysis – TCP‑FC‑001 run‑001

## Purpose

Determine whether a passive observer can infer that receiver flow‑control limited the sender.

## Source artifacts

* Capture: `/home/rosa/experiments/tcp/TCP-FC-001/run-001/tcp_capture.pcap`
* Sender timeline: `/home/rosa/experiments/tcp/TCP-FC-001/run-001/sender_timeline.log`

## Controlled workload facts (provided)

* Sender transmitted 134 217 728 bytes (128 MiB).
* Receiver pause duration ≈ 300.180 ms (controlled).

## TCP handshake and window‑scale negotiation

* SYN raw window = 64240, WSCALE = 7, MSS = 1460
* SYN‑ACK raw window = 65160, WSCALE = 7, MSS = 1460

## Advertised receiver window evolution (scaled)

* Minimum raw advertised window = 0
* Minimum scaled advertised window = 0
* Zero‑window advertised: yes (count = 57)

## Passive usable credit

* Minimum passive usable credit = -128459104
* Zero‑credit observed: no
* New data advanced during zero‑credit: no

## Retransmission / duplicate sequence evidence

* Detected: no

## Sender send() timing

* Maximum send() duration = 260646331 ns (event `post_send`)
* Timestamp of max duration = 1791402958271582440

## Classification (observer perspective)

* INSUFFICIENT / AMBIGUOUS PASSIVE EVIDENCE

## Limitations and observations

* Clock synchronization between VM1 (pcap) and VM2 (application timestamps) is only approximate.
* No explicit zero‑window advertisement was observed; credit calculations rely on scaled windows.
* The analysis does not model fast‑retransmit or other TCP nuances beyond the RFC‑based credit model.
