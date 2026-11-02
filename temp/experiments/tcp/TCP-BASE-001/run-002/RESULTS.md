# TCP-BASE-001 Run 002 Results

## Date

2026-10-07

## Environment

- hostname: **sriov-vm1**
- kernel: **Linux 6.8.0-146-generic**
- TCP congestion control: **cubic**
- ens4 IP: **192.168.88.20/24**
- MTU: **1500**
- iperf3 version: **3.16**
- tcpdump version: **4.99.4**

## Workload

```bash
iperf3 -c 192.168.88.21 -t 2 -i 1
```

**iperf3 exit code:** `0`

**Sender result**

```text
7.42 GBytes transferred
31.9 Gbits/sec
49 retransmissions
```

**Receiver‑reported result**

```text
7.42 GBytes
31.8 Gbits/sec
```

iperf3 reported **49 sender retransmissions**; their cause was not
analyzed in TCP‑BASE‑001.

## Capture result

- packets captured: **186200**
- packets received by filter: **186200**
- packets dropped by kernel: **0**
- pcap size: **23901464 bytes**

## Observed TCP connections

```text
192.168.88.20:54028 <-> 192.168.88.21:5201
192.168.88.20:54030 <-> 192.168.88.21:5201
```

**Confirmed bulk‑data connection**

```text
192.168.88.20:54030 <-> 192.168.88.21:5201
```

(The connection on port 54028 carries no bulk data and is not used for
the iperf3 transfer.)

## Bulk‑flow validation

- **SYN:** present  
- **SYN‑ACK:** present  
- **final handshake ACK:** present  
- **sender data:** present  
- **reverse ACKs:** present  
- **FIN:** not observed  
- **RST:** observed (used for termination)

## Result

TCP‑BASE‑001 run‑002 **successfully validated** the raw passive TCP
capture pipeline.  Evidence collection succeeded, enabling downstream
analysis.  This does **not** imply any diagnosis of application,
flow‑control, or congestion‑control state.

## Artifacts

- `environment.txt`  
- `sender.log`  
- `iperf_exit_code`  
- `tcp_capture.pcap`  
- `capture_stats.txt`  
- `pcap_head.txt`  
- `pcap_tail.txt`  
- `connection_stats.txt`  
- `RESULTS.md`
