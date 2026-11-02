# RUN‑004 PLAN – TCP‑FC‑001 measurement‑quality repeat of run‑002

## Purpose

* Run‑004 is a **valid** measurement‑quality repeat of run‑002.
* The TCP workload (sender → receiver) is **identical** to run‑002 and run‑003:
  - Destination: `192.168.88.21:5203`
  - Total payload: **128 MiB**
  - Application write size: **64 KiB**
  - Continuous writes – no sleeps
  - Receiver configuration:
    - `NORMAL_READ_BYTES = 256 KiB`
    - `PAUSE_SEC = 0.300 s`
    - Default socket buffers, MTU 1500, cubic, offloads unchanged

## Reason for run‑004

* **run‑003** was *invalid* because the sender could not connect (ConnectionRefusedError) and the captured traffic was unrelated/previous data.
* All artifacts from run‑003 have been **preserved** (no deletion or modification).

## Measurement change only

* The only intentional change relative to run‑002 is the **tcpdump capture buffer**:
  `-B 32768` (32 MiB) – this achieved **zero kernel drops** in run‑003 and will be retained.

---

*Document version: 1.0 – 2026‑10‑07*
