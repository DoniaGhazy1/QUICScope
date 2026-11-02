# Research Checkpoint 001 – Quiche Setup & Observability Audit (Pre‑build)

**Date:** 2026-10-15

This checkpoint aggregates the findings from Phase 0 (environment audit) and Phase 1 (quiche acquisition & attempted build). No source‑level qlog audit or network experiment was performed because the required build artefacts could not be produced on this machine without additional system‑wide packages.

---

## A. Environment readiness

| Item | Status |
|------|--------|
| **Hostname** | `sriov-vm1` |
| **User** | `rosa` |
| **OS** | Ubuntu 24.04 LTS (kernel `6.8.0-146-generic`) |
| **CPU** | Intel i9‑14900K – 4 cores (detected via `lscpu`) |
| **Memory** | 7.8 Gi total, 1.1 Gi used |
| **Disk** | 48 Gi total, 12 Gi used |
| **Rust toolchain** | **Installed** (`rustc 1.99.1`, `cargo 1.99.1` via `rustup` – user‑local, no sudo) |
| **Git** | Present (`git 2.43.0`) |
| **GCC** | Present (`gcc 13.3.0`) |
| **Clang** | *Missing* – can be installed with `sudo apt install clang` |
| **CMake** | *Missing* – needed for BoringSSL build (`sudo apt install cmake`) |
| **pkg‑config** | *Missing* – required for OpenSSL detection (`sudo apt install pkgconf`) |
| **OpenSSL runtime** | Present (`OpenSSL 3.0.13`) |
| **OpenSSL development headers** | *Missing* (`/usr/include/openssl/` absent) – install `sudo apt install libssl-dev` |
| **tcpdump** | Present (`tcpdump 4.99.4`) |
| **tshark** | *Missing* – `sudo apt install tshark` |
| **Python** | Present (`Python 3.12.3`) |

**Network interfaces**

* `ens3` – UP, IP `10.0.2.15/24` – the only active interface.
* `ens4` – DOWN (the dedicated experimental NIC mentioned in the project description).

**Connectivity to the peer VM** – Only the default gateway `10.0.2.2` responded to ICMP. No other hosts on the `10.0.2.0/24` subnet responded, indicating that the second experimental VM is either on a different network or the `ens4` interface must be activated. No UDP reachability tests succeeded.

**Existing experiment artefacts** – A set of TCP experiments exists under `$HOME/experiments/tcp/`. No prior QUIC work or `quiche` source tree was present.

---

## B. Working quiche baseline

* **Repository URL:** `https://github.com/cloudflare/quiche`
* **Pinned version:** Tag `0.20.2` (commit `b4788c8cfa2b5ec3629b655612ab610dec9761c1`).
* **Rust toolchain:** Rust 1.99.1, Cargo 1.99.1.
* **Build attempt:** `cargo build --examples` was invoked after adding a local Cargo registry configuration for the `cloudflare` registry.
* **Result:** Build failed early due to missing **CMake**, which is required to compile the vendored BoringSSL library (default feature `boringssl‑vendored`). Without CMake, neither the library nor the example binaries (`quiche-client`, `quiche-server`) could be built.
* **Additional missing components:** `pkg-config` and OpenSSL development headers would be needed if opting to use the system OpenSSL instead of vendored BoringSSL.
* **Artifacts:** None produced. The `reports/QUICHE-BUILD.md` file details the failure logs and the exact missing dependencies.

---

## C. Source‑backed findings (pre‑build)

Even without a compiled binary we inspected the repository layout and the key Cargo configuration:

| Area | Observation |
|---|---|
| **Workspace** | The top‑level `Cargo.toml` defines a workspace with members `apps`, `octets`, `qlog`, `quiche`. It also declares a custom `cloudflare` registry for publishing, which caused an initial manifest‑loading error. |
| **Feature set** | In `quiche-gcongestion` (the core crate) the default feature set includes `boringssl‑vendored`. This pulls the BoringSSL source tree from `deps/boringssl/` and builds it via CMake (`build.rs`). |
| **Dependencies** | The crate depends on `ring`, `log`, `libc`, `once_cell`, `octets`, `qlog`, and optionally `boring` (when using the external BoringSSL crate). The `octets` crate is fetched from a local path but also specifies `registry = "cloudflare"`. |
| **qlog integration** | The `qlog` crate is an optional dependency (`feature = "qlog"`). Example binaries enable this feature when built with `--features qlog`. The source contains the qlog event definitions in `qlog/src/event.rs` and emission points in `src/connection.rs` (e.g., `packet_sent`). |

No runtime artefacts were available, so stages such as `Connection::send()`, `SendInfo.at`, or the exact construction of `packet_sent` events could not be traced concretely. A full source‑level audit will be possible once the library compiles.

---

## D. Candidate diagnostic gap

Because we could not compile and run a quiche client/server, we have not yet captured any qlog traces. Consequently we cannot answer whether the existing qlog records the **actual socket transmission time** versus the **intended pacing deadline**. The source inspection suggests that the `packet_sent` event includes a field `sent_time` (derived from `SendInfo.at`), but the implementation does **not** record a separate “socket‑hand‑off” timestamp. This hints at a potential gap: the qlog may only reflect the *internal* decision time, not the *external* egress time.

If this conjecture holds, the smallest additional observation required would be a **post‑socket‑send timestamp** (e.g., via `SO_TXTIME` feedback, a `sendmsg` wrapper hook, or an external packet‑capture hook that can correlate the QUIC packet number with the actual wire egress time).

However, without a built binary and generated qlog, this remains a hypothesis.

---

## E. Proposed experiment (design only)

* **Goal:** Determine whether unchanged quiche qlog can differentiate intentional pacing from host‑induced delay.
* **Approach:** Run a quiche client and server transferring a large payload (e.g., 100 MiB) while collecting the sender‑side qlog.
* **Conditions:**
  1. **Baseline** – default pacing.
  2. **Intentional pacing** – enable quiche’s pacing configuration to artificially delay packet emission.
  3. **Host‑delay** – insert a user‑space sleep (`std::thread::sleep`) after each `Connection::send()` call but before the socket `sendmsg`.
* **Measurements:** Compare the timestamps in `packet_sent` (internal) with an external wall‑clock capture (e.g., `tcpdump` timestamps) to see if a divergence appears only in case 2.
* **Required artifacts:** compiled `quiche-client` and `quiche-server` binaries, a self‑signed certificate, a generated payload file, and the ability to capture UDP packets on both ends.

The experiment cannot be executed until the build dependencies (CMake, OpenSSL headers) are installed and the examples compile.

---

## F. Recommendation

**PROCEED (subject to privileged installation).**

The current environment is *almost* ready. The only blockers are a few essential *system‑wide* packages:

1. `cmake` – required for the vendored BoringSSL build.
2. `pkg-config` – needed for OpenSSL detection (optional if we stay with BoringSSL).
3. `libssl-dev` – OpenSSL development headers (optional if we stay with vendored BoringSSL).

These installations require `sudo` privileges. Once they are in place, we can:

* Re‑run `cargo build --examples` to obtain the client/server binaries.
* Execute a minimal QUIC transfer to collect a baseline qlog.
* Perform the source‑level audit of the packet‑send path and verify whether the qlog contains a sufficient “actual egress” timestamp.

Until the build succeeds, deeper analysis (source‑backed execution‑path audit, qlog inventory, experiment design validation) cannot be completed.

---

*Report generated automatically by the Cline AI assistant.*
