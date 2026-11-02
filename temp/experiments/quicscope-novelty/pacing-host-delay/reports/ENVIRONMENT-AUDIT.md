# Environment Audit Report

**Generated on:** 2026-10-15

## 1. Host Identity

- **Hostname:** sriov-vm1
- **Username:** rosa
- **Operating System:** Ubuntu 24.04 LTS (kernel `6.8.0-146-generic`)
- **Architecture:** x86_64

## 2. Hardware Resources

- **CPU:** Intel(R) Core(TM) i9-14900K (4 cores, 1 thread per core, 13.3 GHz max, 64 KB L1d, 64 KB L1i, 16 MiB L2, 16 MiB L3)
  - Detected via `lscpu`.
- **Memory:** 7.8 Gi total, 1.1 Gi used, 6.4 Gi free (via `free -h`).
- **Disk:** `/dev/vda1` 48 Gi total, 12 Gi used, 37 Gi free (via `df -h $HOME`).

## 3. Installed Development Tools

| Tool | Version / Status | Notes |
|------|------------------|-------|
| **Git** | `git version 2.43.0` | Available (via `git --version`). |
| **Rustc** | *not found* | `rustc` command missing. Installable via `rustup` (user‑local, no sudo required). |
| **Cargo** | *not found* | `cargo` command missing. Installable via `rustup`. |
| **GCC** | `gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0` | Available. |
| **Clang** | *not found* | Could be installed via `sudo apt install clang`. |
| **CMake** | *not found* | Could be installed via `sudo apt install cmake`. |
| **Pkg‑config** | *not found* | Required for locating OpenSSL headers/libraries. Installable via `sudo apt install pkgconf`. |
| **OpenSSL (runtime)** | `OpenSSL 3.0.13 30 Jan 2024` | Runtime library present (`openssl version`). Header files missing (`/usr/include/openssl/` not found). |
| **Python** | `Python 3.12.3` | Available (`python3 --version`). |
| **tcpdump** | `tcpdump version 4.99.4` | Available. |
| **tshark** | *not found* | Could be installed via `sudo apt install tshark`. |

## 4. Network Interfaces & Connectivity

### Interface Overview (`ip -br addr show`)

```
lo               UNKNOWN        127.0.0.1/8 ::1/128
ens3             UP             10.0.2.15/24 metric 100 fec0::5054:ff:fe12:3456/64 fe80::5054:ff:fe12:3456/64
ens4             DOWN
```

### Routing Table (`ip route`)

```
default via 10.0.2.2 dev ens3 proto dhcp src 10.0.2.15 metric 100
10.0.2.0/24 dev ens3 proto kernel scope link src 10.0.2.15 metric 100
10.0.2.2 dev ens3 proto dhcp scope link src 10.0.2.15 metric 100
10.0.2.3 dev ens3 proto dhcp scope link src 10.0.2.15 metric 100
```

The primary network interface `ens3` is up with address `10.0.2.15/24`. The secondary experimental interface `ens4` is currently down.

### Reachability Tests

* Ping to the default gateway `10.0.2.2` – **successful**.
* Ping attempts to adjacent IPs (`10.0.2.14‑20`) – only `10.0.2.15` (this host) responded. No other VM on the same subnet could be reached.

**Conclusion:** The remote experimental VM is not currently reachable on the `ens3` network, and `ens4` is down. Additional network configuration (or activation of `ens4`) will be required to communicate with the peer VM.

## 5. Existing Experiment Directories

The home directory contains a previous set of TCP experiments under `$HOME/experiments/tcp/`. No `quicscope-novelty` workspace exists yet, and no existing `quiche` source trees were found under `$HOME`.

## 6. Source Code Inspection

No local copy of the Cloudflare `quiche` repository is present. The only references to `qlog` in the current code base are documentation files (`docs/semantic-model.md`).

## 7. Summary of Missing Essentials for Quiche Build

1. **Rust toolchain** – `rustc`/`cargo` not installed (installable via user‑local `rustup`).
2. **OpenSSL development headers** – `pkg-config` missing, and `/usr/include/openssl/` is absent. Installing `libssl-dev` (requires sudo) or bundling BoringSSL is needed.
3. **Build utilities** – `clang` (optional), `cmake` (optional), and `pkg-config` are missing; they are typically required for the quiche build process.
4. **Network connectivity** – The peer VM cannot be reached on the current interface; `ens4` must be brought up or the correct peer IP must be supplied.

## 8. Next Steps (Pending Permissions & Information)

* **Install Rust toolchain** – can be done without elevated privileges.
* **Obtain OpenSSL dev headers** – requires `sudo apt install libssl-dev` (or equivalent). Permission needed.
* **Activate or configure the experimental network interface `ens4`** – may need admin rights or coordination with the VM manager.
* **Acquire the peer VM’s IP address** – to verify UDP connectivity.

These actions are prerequisites for the subsequent Phase 1 (quiche acquisition & build) and Phase 2 (testbed verification).

---
*Report generated automatically by the Cline AI assistant.*
