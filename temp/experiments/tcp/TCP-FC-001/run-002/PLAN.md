# Run‑002 PLAN – TCP‑FC‑001 active‑limiter validation

## Purpose

Observe the passive‑observer TCP transition defined by the methodology:

* **Positive receiver credit** + **new‑data progress**
* **Zero receiver credit** with the sender’s high‑water mark remaining **stationary** for a non‑zero interval while the application continues offering data
* **Positive receiver credit** again with **new‑data progress** resumed

## Single experimental change (relative to run‑001)

* **Receiver controlled pause** – after the receiver has consumed roughly **256 KiB** of the client payload, it invokes a **300 ms** no‑`recv()` pause (i.e., `time.sleep(PAUSE_SEC)`).
* All other workload and environment parameters remain unchanged:
  * total sender payload = **128 MiB**
  * sender write size = **64 KiB** per `send()`
  * sender continuously writes (no artificial sleeps)
  * TCP port = **5203**
  * default socket buffer sizes on both ends
  * MTU = **1500** (unchanged)
  * off‑loads unchanged
  * congestion‑control algorithm unchanged (cubic)
  * no sysctl/kernel changes

## Pre‑declared success criterion (phases A → B → C)

* **PHASE A** – `passive_usable_receive_credit > 0` **and** new sender sequence‑space progress is observed.
* **PHASE B** – `passive_usable_receive_credit == 0`; after accounting for data already emitted/off‑loaded, the sender’s sequence‑space high‑water remains **stationary** for a non‑zero sustained interval while the controlled application continues to attempt to supply data.
* **PHASE C** – `passive_usable_receive_credit > 0` again **and** new sender sequence‑space progress resumes.

No requirement that the stall start at the exact first zero‑window packet, and no arbitrary minimum stall duration is imposed.

## Important semantic limits (observer notes)

* Continuous application writes **support** the assumption that the sender is back‑logged, but they do **not** constitute exact proof that the endpoint’s send buffer is full (`D = true`).
* **Exact D** (receiver‑flow‑control being the active limiter) is endpoint‑internal and would require kernel‑level metrics such as `sndbuf` occupancy.
* **Exact C** (congestion‑control limitation) is also endpoint‑internal; passive loss/recovery evidence can suggest congestion but its absence does **not** prove `C = false`.
* A zero‑advertised window provides strong evidence that **F = false**, but on its own does not establish the full predicate `RECEIVER_FLOW_CONTROL_LIMITED` (`D ∧ ¬F ∧ C`).
* `observed_snd_nxt` is a **passively reconstructed** value and may differ from the kernel’s actual `SND.NXT`.

---

*Document version: 1.0 – 2026‑10‑07*