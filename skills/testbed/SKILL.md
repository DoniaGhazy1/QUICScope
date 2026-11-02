# Skill: Testbed Verification

Use this skill before transport experiments.

## Objective

Establish that VM1 and VM2 are reachable and that experimental traffic
will traverse ens4.

## VM1

Run:

    hostname
    ip -br addr
    ip route get 192.168.88.21
    ethtool ens4

Expected experimental address:

    192.168.88.20/24

Expected route to VM2:

    dev ens4

## VM2

Run:

    hostname
    ip -br addr
    ip route get 192.168.88.20
    ethtool ens4

Expected experimental address:

    192.168.88.21/24

## Connectivity

From VM1:

    ping -c 5 192.168.88.21

Do not proceed with performance experiments if traffic routes through
ens3.

## Record

Save verification output with the experiment metadata.
