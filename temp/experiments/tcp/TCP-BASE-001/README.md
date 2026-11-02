# TCP-BASE-001: Passive TCP Baseline

## Purpose

This experiment validates the passive TCP evidence collection pipeline
before any controlled APP/FC/CC/LOSS experiments are run.  It is **not**
intended to diagnose a limiting state; rather it demonstrates that the
observer on VM1 can capture the raw TCP packets required for later
analysis.

The observer is located on **VM1** and captures TCP traffic on interface
`ens4`.

## Testbed

**VM1 – sender / observer**
- hostname: `sriov-vm1`
- experimental interface: `ens4`
- experimental IP: `192.168.88.20/24`
- Mellanox SR-IOV VF
- role: iperf3 client **plus** passive `tcpdump` observer

**VM2 – receiver**
- hostname: `sriov-vm2`
- experimental interface: `ens4`
- experimental IP: `192.168.88.21/24`
- Mellanox SR-IOV VF
- role: iperf3 server

**Traffic path**

```
VM1 ens4 (192.168.88.20)
        |
        | TCP
        |
VM2 ens4 (192.168.88.21)
```

The management interface `ens3` is **not** used for this experiment and
must remain untouched.

## Important temporary network configuration

The `ens4` addresses/configuration are temporary for the experiment and
may need to be restored before each run.

**VM1**

```bash
sudo ip link set dev ens4 up
sudo ip addr add 192.168.88.20/24 dev ens4
```

**VM2**

```bash
sudo ip link set dev ens4 up
sudo ip addr add 192.168.88.21/24 dev ens4
```

`ip addr add` will report “Address already assigned” if the address is
already present; in that case do not delete/re‑add it.

## Pre‑run verification

### VM1

```bash
ip -br link show ens4
ip -br addr show ens4
ip route get 192.168.88.21
ping -I ens4 -c 5 192.168.88.21
```

### VM2

```bash
ip -br link show ens4
ip -br addr show ens4
ip route get 192.168.88.20
ping -I ens4 -c 5 192.168.88.20
```

All checks must succeed before proceeding.

## Receiver setup

On VM2 start the iperf3 server:

```bash
iperf3 -s -1
```

The `-1` flag makes the server exit after a single client session.
The server must be listening before the sender workload starts.

## Passive capture

On VM1 create a **new** run directory (never overwrite an existing one).

Start `tcpdump` on `ens4` with:

- snaplen: **128 bytes**
- TCP port: **5201**
- hosts: **192.168.88.20** and **192.168.88.21**

Equivalent filter:

```
tcp port 5201 and host 192.168.88.20 and host 192.168.88.21
```

Save the raw capture as `tcp_capture.pcap` and the `tcpdump` stderr /
statistics as `capture_stats.txt`.  Verify that `tcpdump` is alive
before starting the iperf3 client.

## Sender workload

On VM1 run:

```bash
iperf3 -c 192.168.88.21 -t 2 -i 1
```

Save stdout/stderr as `sender.log` and record the exit code.

## Capture shutdown

After `iperf3` finishes:

1. Wait ~1 second (to capture termination packets).  
2. Send `SIGINT` to the `tcpdump` process.  
3. Wait for `tcpdump` to exit.  
4. Preserve the capture statistics.  
5. **Never** overwrite the raw `pcap`.

## Raw validation

Using `tcpdump` (no tshark required), verify that the capture contains:

- SYN, SYN‑ACK, final handshake ACK
- sender data packets
- receiver ACKs
- connection termination (FIN or RST)

Do **not** assume all traffic on port 5201 belongs to a single TCP
connection; identify connections by their 4‑tuple (src IP:port ↔ dst IP:port).

## Success criteria

TCP‑BASE‑001 is considered successful when:

- `iperf3` exits with code 0 (successful transfer).  
- A raw `pcap` file is produced.  
- The TCP three‑way handshake is present.  
- Bulk data packets are present.  
- Reverse ACKs are present.  
- Capture statistics are available and kernel drops are negligible.  
- The bulk‑data connection can be identified among any other
  port‑5201 streams.

**Do NOT** define success based on:

- achieving a particular throughput,  
- zero retransmissions,  
- proving a congestion state, or  
- proving a loss‑free network.

## Evidence classification

This experiment only establishes the passive observation pipeline.
It does **not** infer any higher‑level state such as:

- `APPLICATION_LIMITED`  
- `RECEIVER_FLOW_CONTROL_LIMITED`  
- `CONGESTION_CONTROL_LIMITED`  
- recovery state  

Run‑001 is preserved as a failed preliminary run because the intended
iperf3 client received “Connection refused”.  Run‑002 is the successful
baseline measurement.
