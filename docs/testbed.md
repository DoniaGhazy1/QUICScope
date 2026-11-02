# QUICScope Experimental Testbed

## Physical Topology

                    100G network
        ┌────────────────────────────────┐
        │                                │
      DEIMOS                           PHOBOS
        │                                │
      Docker                           Docker
        │                                │
      QEMU                             QEMU
        │                                │
      VM1                              VM2
        │                                │
      ens4 ─────────────────────────── ens4
192.168.88.20                     192.168.88.21

## Physical Hosts

VM1 host:

    deimos.cs.vt.edu

VM2 host:

    phobos.cs.vt.edu

## Guest Management

VM1 SSH is forwarded through deimos.

VM2 SSH is forwarded through phobos.

The local SSH aliases are:

    ssh vm1
    ssh vm2

## Guest Interfaces

Both VMs contain a QEMU management interface and a passed-through
Mellanox SR-IOV VF.

Management:

    ens3
    commonly 10.0.2.15

Experiment:

    ens4

VM1 experiment address:

    192.168.88.20/24

VM2 experiment address:

    192.168.88.21/24

All transport experiments must use ens4.

## NIC

The experiment interface is a Mellanox ConnectX-family SR-IOV VF.

Expected reported link speed:

    100000 Mb/s

Check using:

    ethtool ens4

## Connectivity Verification

VM1:

    ip addr show ens4
    ip route get 192.168.88.21
    ping 192.168.88.21

VM2:

    ip addr show ens4
    ip route get 192.168.88.20
    ping 192.168.88.20

## Temporary IP Configuration

If addresses disappear after VM restart:

VM1:

    sudo ip addr add 192.168.88.20/24 dev ens4
    sudo ip link set ens4 up

VM2:

    sudo ip addr add 192.168.88.21/24 dev ens4
    sudo ip link set ens4 up

Do not assume these addresses are persistent until persistent network
configuration has been explicitly verified.

## Important

Never accidentally benchmark ens3.

Before an experiment verify:

    ip route get <peer>

The result must identify ens4.
