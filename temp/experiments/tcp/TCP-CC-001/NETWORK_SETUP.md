# Network Setup – TCP‑CC‑001

The research uses two VMs (VM 1 – *sender*, VM 2 – *receiver*) connected via a private
network on the **ens4** interface of each host.  The following sections capture the
configuration **after all corrective actions** have been applied.

---

## VM 1 (sender)

*Interface*: `ens4`
*IP address*: `192.168.88.20/24`
*Link‑local IPv6*: `fe80::1040:d5ff:fe16:cb13/64`
*Routing to VM 2*: 
```bash
$ ip route get 192.168.88.21
192.168.88.21 dev ens4 src 192.168.88.20 uid 1000
    cache
```
*Neighbour entry for VM 2*: 
```bash
$ ip neigh show 192.168.88.21
192.168.88.21 dev ens4 lladdr 1a:a8:64:fb:12:09 REACHABLE
```
*Ping verification* (3 packets, 0 % loss):
```bash
$ ping -I ens4 -c 3 -W 2 192.168.88.21
3 packets transmitted, 3 received, 0% packet loss
```

---

## VM 2 (receiver)

*Interface*: `ens4`
*IP address*: `192.168.88.21/24`
*Neighbour entry for VM 1* (observed from VM 1; VM 2 is reachable):
```bash
$ ip neigh show 192.168.88.20
192.168.88.20 dev ens4 lladdr <receiver‑MAC> REACHABLE
```
*(The exact MAC address on VM 2 is not required for the analysis.)*

---

## Summary of changes (pre‑ and post‑correction)
| Item | Before correction | After correction |
|------|-------------------|------------------|
| VM 1 `ens4` IPs | `192.168.88.20/24` **and** `192.168.88.21/24` (duplicate) | `192.168.88.20/24` only |
| VM 2 `ens4` IPs | Duplicate of VM 1 address present (removed) | `192.168.88.21/24` only |
| Route to peer | `local` via `lo` (due to duplicate) | Direct via `ens4` |
| ARP/Neighbour state (VM 1 → VM 2) | `FAILED` | `REACHABLE` |

All commands referenced above are stored in the artefacts directory:
* `/home/rosa/experiments/tcp/TCP-CC-001/monitor/smoke-1791488316-YJK6/` – contains the ping output and neighbour checks performed immediately before the successful smoke test.
