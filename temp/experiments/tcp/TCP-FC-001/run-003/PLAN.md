# RUN-003 PLAN – TCP-FC-001 measurement-quality repeat of run-002

Purpose: measurement-quality repeat of run-002 with larger tcpdump capture buffer.

Experimental workload (identical to run-002):
- Sender: destination 192.168.88.21:5203, total payload 128 MiB, write size 64 KiB, continuous writes.
- Receiver: NORMAL_READ_BYTES = 256 * 1024, PAUSE_SEC = 0.300, default socket buffers.

Measurement change only: increase tcpdump capture buffer using -B 32768.

Run-002 tcpdump command (reference):
```
sudo -n tcpdump -i ens4 -w /home/rosa/experiments/tcp/TCP-FC-001/run-002/capture.pcap -s 0 -nn tcp port 5203 > /home/rosa/experiments/tcp/TCP-FC-001/run-002/tcpdump.log 2>&1 &
```

Proposed run-003 tcpdump command:
```
sudo -n tcpdump -i ens4 -B 32768 -w /home/rosa/experiments/tcp/TCP-FC-001/run-003/capture.pcap -s 0 -nn tcp port 5203 > /home/rosa/experiments/tcp/TCP-FC-001/run-003/tcpdump.log 2>&1 &
```

Success criteria remain unchanged (Phase A, B, C as defined). Additional capture quality criterion: aim for zero kernel drops.

---

*Document version: 1.0 – 2026-10-07*
