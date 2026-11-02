# TCP-FC-001 – Passive‑Observer Methodology

This document defines how a passive TCP observer should reconstruct the
receiver‑flow‑control state that corresponds to the QUICScope predicate
**F = FlowControlAllowsNewData**.  It freezes the methodology that will be used
for run‑002.

---

## 1. Semantic Goal

**F** is true **iff** the remote endpoint has *advertised* a non‑zero receive
window that would permit at least one new data byte to be transmitted,
assuming no other limiter (congestion‑control, application‑limited send
buffer, etc.) interferes.

---

## 2. TCP Mapping of **F**

The sender can transmit new data only when

```
advertised_right_edge > snd_nxt_observed
```

where
* `advertised_right_edge = SEG.ACK + (SEG.WND << wscale)`  (RFC 9293),
* `snd_nxt_observed` is the highest data sequence number the observer has
  seen on the wire.

The passive receive credit is therefore

```
credit = advertised_right_edge - snd_nxt_observed
```.

---

## 3. TCP Sender‑Side Window State (RFC 9293)

* **SND.UNA** – oldest un‑acknowledged byte.
* **SND.NXT** – next byte the sender will transmit.
* **SND.WND** – current send‑window size (bytes).
* **SND.WL1** – ACK number of the last window update.
* **SND.WL2** – SEQ number of the segment that carried that update.
* **SEG.SEQ** – sequence number of an incoming ACK segment.
* **SEG.ACK** – cumulative acknowledgement number carried in the ACK.
* **SEG.WND** – raw advertised window field.
* **wscale** – window‑scale factor negotiated in the SYN exchange.

The *actual* sender state lives inside the kernel; a passive observer must
reconstruct it from packets.

---

## 4. Passive‑Observer Reconstruction vs. Actual Sender State
## 5. Window‑Update Acceptance (RFC 9293 §3.9.2)

When an ACK segment `SEG` arrives, the observer first validates the ACK range
according to the RFC (the actual kernel state uses `SND.UNA` and `SND.NXT`):

```
SND.UNA <= SEG.ACK <= SND.NXT
```

Only after this validation does the observer apply the RFC‑defined window‑
update condition for the **ESTABLISHED** state:

```
SND.WL1 < SEG.SEQ
   OR
(SND.WL1 == SEG.SEQ && SND.WL2 <= SEG.ACK)
```

If the condition holds, the window state is updated as defined by RFC 9293:

```
SND.WND <- SEG.WND
SND.WL1 <- SEG.SEQ   // stores SEG.SEQ of the segment used for the update
SND.WL2 <- SEG.ACK   // stores SEG.ACK of the segment used for the update
```

-----

**Observer pseudocode** (applied to each inbound ACK segment).  The observer
maintains **reconstructed** state variables (`recon_una`, `recon_nxt`,
`recon_wnd`, `recon_wl1`, `recon_wl2`).  `observed_snd_nxt` is maintained
separately from data packets and represents the highest sequence number seen on
the wire.

```pseudo
// Reconstructed sender variables: recon_una, recon_nxt, recon_wnd,
// recon_wl1, recon_wl2
// Segment fields: seg_seq, seg_ack, seg_wnd
// observed_snd_nxt: highest data SEQ observed from client→server

// 1. Advance reconstructed SND.UNA (recon_una) on any cumulative ACK that
//    acknowledges new data.
if seg_ack > recon_una {
    // Normal cumulative ACK – advance recon_una
    recon_una = seg_ack
    // If the ACK jumps beyond what we have observed, record a reconstruction gap.
    if seg_ack > observed_snd_nxt {
        // Record that the capture is missing some data (e.g., increment a gap counter)
        record_observer_gap(seg_ack - observed_snd_nxt)
    }
}

// 2. Apply the RFC window‑update rule.
if (recon_wl1 < seg_seq) || (recon_wl1 == seg_seq && recon_wl2 <= seg_ack) {
    recon_wnd = seg_wnd
    recon_wl1 = seg_seq   // store SEG.SEQ
    recon_wl2 = seg_ack   // store SEG.ACK
}
```

The observer must preserve the exact ordering and comparison semantics of the
RFC to avoid stale‑window bugs.  Note that `recon_nxt` (the reconstructed SND.NXT)
is **not** updated here; it is derived separately from data‑packet capture and
may differ from the kernel’s actual `SND.NXT`.
    snd_wl1 = seg_seq
    snd_wl2 = seg_ack
}
```

The observer must maintain the same ordering and comparison semantics as the
kernel to avoid stale‑window bugs.

---

## 6. Passive‑Observer State Variables (minimum required)

| Variable | Meaning (reconstructed) | Updated by | Direct / Derived |
|---|---|---|---|
| `reconstructed_snd_una` | Highest ACK seen (oldest un‑acked byte) | ACK field of any inbound ACK | **WIRE_DERIVED** |
| `observed_snd_nxt` | Highest data SEQ seen from client→server | SEQ/SEQ+LEN of data packets (TSO/GSO included) | **WIRE_DERIVED** |
| `reconstructed_snd_wnd` | Scaled advertised window from most recent accepted update | SEG.WND of an ACK that satisfies the RFC update rule | **WIRE_DERIVED** |
| `reconstructed_snd_wl1` | SEG.SEQ of the segment used for the last accepted window update | Same ACK segment that updated `reconstructed_snd_wnd` | **WIRE_DERIVED** |
| `reconstructed_snd_wl2` | SEG.ACK of the segment used for the last accepted window update | Same segment that updated `reconstructed_snd_wnd` | **WIRE_DERIVED** |
| `reconstructed_advertised_right_edge` | `reconstructed_snd_una + reconstructed_snd_wnd` | Computed after each accepted update (initial value from SYN‑ACK) | **WIRE_DERIVED** |

All updates obey the RFC rule from §5.

---

## 7. Passive Usable Receive‑Credit Derivation

The RFC defines the usable send window as:

```
U = SND.UNA + SND.WND – SND.NXT
```

From the passive‑observer’s perspective the analogue is:

```
passive_usable_receive_credit = reconstructed_snd_una
                                 + reconstructed_snd_wnd
                                 - observed_snd_nxt
```

* `reconstructed_snd_una`, `reconstructed_snd_wnd` and `observed_snd_nxt` are
  **wire‑derived** values maintained by the observer (see §6).
* This formula **reconstructs** the sender’s flow‑control state – it is a
  passive reconstruction of the RFC sender usable window – and is not the
  kernel’s actual `U` variable.  Mixing a newly‑advanced `SND.UNA` with a stale
  `SND.WND` would produce an incorrect credit, so the observer must follow the
  RFC‑defined update order described in §5.

The derived credit has the same interpretation as the generic `credit`
definition used elsewhere:

* **credit > 0** → receiver advertises enough space for new data; **F = true**.
* **credit = 0** → receiver offers no space; **F = false** (receiver flow‑control
  is the active limiter).
* **credit < 0** → reconstruction anomaly (e.g., stale window or capture loss);
  does *not* imply **F = false**.

---

## 8. Zero‑Window Interpretation

* **WIRE_DIRECT** – raw `Window` field in an ACK is `0`.
* **WIRE_DERIVED** – after applying the negotiated `wscale`, the effective
  advertised window is `0`.
* **WIRE_INFERRED** – the observer’s **passive usable receive credit** (see
  §7) provides the semantic interpretation:
  * `credit > 0` → passive evidence supports **F = true** (receiver permits new
    data).
  * `credit == 0` → passive evidence supports **F = false** (receiver flow‑
    control is limiting new data).
  * `credit < 0` → reconstruction or capture anomaly; further investigation is
    required and the anomaly does **not** imply any semantic value for **F**.

Even when `credit == 0` the observer cannot conclude that the full predicate
`RECEIVER_FLOW_CONTROL_LIMITED` (i.e., `D ∧ ¬F ∧ C`) holds; it only establishes
**F = false**.  Demonstrating that the stall is due to the receiver (and not to
congestion or application limitation) requires the additional D and C evidence
described in §11.

---

## 9. New‑Data Progress Definition

Progress is recorded when `observed_snd_nxt` strictly increases beyond its
previous maximum, *excluding*:

* retransmissions of already‑seen sequence ranges,
* SYN/FIN sequence‑space consumption (accounted separately),
* wrap‑around handling (mod 2³²),
* zero‑window probes (`LEN = 0`), and
* intermediate sequence numbers hidden by TSO/GSO (the observer uses the right
  edge of each captured segment).

---

## 10. Active‑Limiter Success Criterion (run‑002)

The passive observer must see the following three phases **in order**:

1. **Phase A** – `credit > 0` **and** `observed_snd_nxt` shows new‑data progress
   (strictly increasing).
2. **Phase B** – `credit == 0`.  After accounting for any data already emitted
   or off‑loaded (i.e., data that may still be in flight when the window closes),
   `observed_snd_nxt` remains *stationary* for a **non‑zero sustained interval**
   while the controlled test harness shows that the application continues to
   attempt to supply data (i.e., pending application payload remains).  The exact
   duration is measured and reported; no arbitrary threshold is imposed.
3. **Phase C** – `credit > 0` again **and** `observed_snd_nxt` resumes increasing.

The phases need not align precisely with the first or last zero‑window packet;
the essential pattern is positive credit → credit zero with a stall → positive
credit again, together with the corresponding progress observations.

---

## 11. Separation of D, F, C Evidence

* **D – Receiver is the active limiter**
  * Direct observation of a zero‑window advertisement.
  * Passive evidence that **application payload has already been submitted to the
    transport but remains unsent or queued at the transport send boundary**.  The
    observer infers this from the fact that `credit == 0` while the sender
    continues to have pending application bytes (as indicated by the controlled
    test harness).  Continuous writes by the application are **supporting**
    evidence that the application is attempting to keep the transport supplied,
    but they are **not** the exact ground‑truth for D.
  * Exact D would require endpoint‑internal metrics (e.g., the kernel’s
    `sndbuf` occupancy, `sk_wmem_queued`, or a socket‑level `ioctl` that reports
    the number of bytes awaiting transmission).
* **C – Congestion‑control limitation**
  * Passive evidence consists of observable loss, retransmission, or recovery
    events (e.g., duplicate ACK bursts, retransmitted segments, ECN marks).  The
    observer records any such events that occur contemporaneously with the
    credit‑zero stall.
  * If **no** loss‑ or retransmission‑related evidence is seen during the stall,
    the observer states: *"No obvious passive evidence supports congestion or
    loss as the cause of the stall; exact C remains endpoint‑internal."
    * This avoids asserting `C = true` without measurement of kernel‑level
    congestion metrics such as `cwnd`.
* **F – Flow‑control allowance** is derived solely from the `credit` calculation
  in §7.

The observer must document supporting evidence for D and explicit exclusion of
obvious C before asserting the active‑limiter hypothesis.

---

## 12. Lessons From Run‑001

| Metric | Observed value |
|---|---|
| `snd_nxt` before first zero‑window | 9 846 785 bytes |
| `snd_nxt` during zero‑window interval | 128 546 089 bytes (final high‑water) |
| `snd_nxt` after first positive window | 128 546 089 bytes |
| Total application payload submitted | 128 MiB (exact) |
| Unique sender‑sequence space captured | ≈ 122.6 MiB (128 546 088 bytes) |

No new sequence‑space progress was observed after the window reopened, so
Phase C of the success criterion was missing.  The ≈ 5.7 MiB difference between
the advertised payload and the captured unique sequence space is **not
established**; while TSO/GSO off‑load is a known capture limitation, it does not
by itself explain the discrepancy.

---

## 13. Run‑002 Experimental Design (minimum workload change)

The **single** experimental intervention is:

* **Receiver controlled pause** – after the receiver has consumed roughly **256 KiB** of the client’s payload, it initiates a **300 ms** no‑`recv()` pause (i.e., stops reading from the socket).  All other parameters remain as in run‑001:
  * total sender payload = 128 MiB
  * sender continuously writes data (no artificial sleeps)
  * application writes of 64 KiB each
  * TCP port 5203
  * default socket buffer sizes
  * unchanged MTU, off‑loads, and congestion‑control algorithm
  * no kernel/sysctl tuning

This intervention is intended to cause the receiver’s advertised window to be exhausted earlier while a substantial amount of unsent payload remains on the sender side, thereby increasing the likelihood of observing the progress → FC‑stall → progress transition.  It does **not** guarantee that `D = true` or that the A → B → C pattern will be realized; it is simply the minimal change designed to make the transition observable.
---

## 14. Freeze Criteria for TCP‑FC‑001

TCP‑FC‑001 may be declared **FROZEN** only when **all** of the following are
met:

1. The passive‑observer reconstruction methodology (sections 3‑7) is defensibly
   derived from RFC 9293 and fully documented.
2. Run‑002 demonstrates the Phase A → B → C pattern defined in §10.
3. All passive evidence is analysed with the methodology; any reconstruction
   anomalies are explicitly reported.
4. Evidence supporting **D** (receiver‑flow‑control limitation) and evidence
   excluding **C** (congestion‑control limitation) are provided.
5. A final D/F/C evidence table justifies the observer’s classification.

If any of the above is missing, the experiment remains in the state
`TCP‑FC‑001 STATUS = NOT FROZEN`.

---

*Document version: 1.0 – 2026‑10‑07*
