# Skill: Controlled TCP Experiment

## Objective

Run a reproducible TCP experiment while collecting both wire and
endpoint evidence.

## Default Roles

VM1:

    TCP sender/client

VM2:

    TCP receiver/server

Unless the experiment specifies otherwise.

---

## Step 1 — Verify path

VM1:

    ip route get 192.168.88.21

Must show:

    dev ens4

---

## Step 2 — Record TCP configuration

VM1:

    sysctl net.ipv4.tcp_congestion_control
    sysctl net.ipv4.tcp_available_congestion_control
    ip link show ens4
    tc qdisc show dev ens4

VM2:

    ip link show ens4
    tc qdisc show dev ens4

---

## Step 3 — Start server

VM2:

    iperf3 -s

---

## Step 4 — Start packet capture

Choose the endpoint appropriate for the experiment.

Example VM1:

    sudo tcpdump -i ens4 -s 0 -w experiment.pcap \
        host 192.168.88.21

---

## Step 5 — Start endpoint observation

During the connection:

    ss -tin dst 192.168.88.21

For repeated samples:

    while true; do
        date +%s.%N
        ss -tin dst 192.168.88.21
        sleep 0.1
    done

Redirect output to a file.

---

## Step 6 — Run workload

Baseline:

    iperf3 -c 192.168.88.21 -t 60

Use one TCP connection by default.

Do not use parallel streams unless the research question requires them.

---

## Step 7 — Preserve artifacts

Store:

    iperf3-client.txt
    iperf3-server.txt
    ss.txt
    experiment.pcap
    metadata.txt
    commands.txt

---

## Step 8 — Interpret

Do not classify based on throughput alone.

Determine:

- Was application data continuously available?
- Was receiver window binding?
- Was congestion control/recovery binding?
- Was loss occurring?
- What was directly visible on the wire?
- What required endpoint state?
