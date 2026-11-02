# TCP‑FC‑001 run‑001 – Final Forensics

This report resolves the contradictions in the earlier reconstruction and
answers the specific questions asked.

---

## 1. Unique sender‑sequence‑space total (as observed in the VM‑1 capture)

- **Client ISN**: `2927657205`
- **First data sequence number** (relative): `1`
- **Final observed high‑water** (relative): `128546089`
- **Unique payload bytes observed**: `128546088` bytes ≈ **122.6 MiB**

**Did the capture already contain the full 128 MiB before the first zero‑window?**
**Answer:** **NO** – before the first zero‑window the high‑water was only
`9846785` bytes (≈ 9.4 MiB).

---

## 2. Sender‑sequence‑high‑water at key moments

| Moment | Timestamp (pcap s) | `snd_nxt` (relative) | Comment |
|---|---|---|---|
| **A – immediately before first zero‑window** | `1791402958.219461` | `9846785` | High‑water after ~10 MiB. |
| **B – during zero‑window interval** | – | `128546089` | `snd_nxt` already at final value while the receiver advertised `win=0`. |
| **C – immediately after first positive‑window** | `1791402958.326701` | `128546089` | No increase after window reopened. |
| **D – end of capture** | – | `128546089` | Unchanged.

**Did new sender sequence space advance after the window reopened?**
**Answer:** **NO** – the high‑water at C equals that at B.

---

## 3. Max‑send call that overlaps the pause

```
post_send timestamp (ns): 1791402958271582440
pre_send  timestamp (ns): 1791402958010936109
duration                : 260646331 ns (≈ 260 ms)
requested bytes         : 65536
accepted  bytes         : 65536
cumulative before call  : 12 386 304 bytes
cumulative after call   : 12 451 840 bytes
```

The call started before the zero‑window and completed after the first positive‑window, but all data were already in the kernel buffer.

---

## 4. Three different quantities

1. **Application bytes accepted by `send()`** – from `sender_timeline.log` – final total **134 217 728 bytes** (exact 128 MiB).
2. **Sender sequence space observed in the capture** – relative sequence numbers – total **128 546 088 bytes** (≈ 122.6 MiB).
3. **Bytes cumulatively ACKed by the receiver** – highest ACK value observed **128 416 465 bytes**.

Because the kernel can buffer data, a blocking `send()` may finish while the
receiver’s advertised window is zero; the data are already queued and will be
transmitted once the window reopens, which is why the timeline shows a `send()`
spanning the pause without new on‑wire sequence advancement.

---

## 5. Correct stateful right‑edge handling (RFC 9293)

* For every ACK (including zero‑window ACKs):
  1. Extract `SEG.ACK` and the raw window `SEG.WND`.
  2. Scale the window: `scaled_win = SEG.WND << wscale` (wscale from the SYN‑ACK).
  3. Compute advertised right‑edge: `right_edge = SEG.ACK + scaled_win`.
* Update the observer’s stored right‑edge **only** if `right_edge` is larger
  than the previously stored value (`max_right_edge`).  This mirrors the TCP
  variables `SND.WL1`/`SND.WL2` and prevents the stale‑window bug.
* Passive usable credit is then `max_right_edge - snd_nxt`, where `snd_nxt`
  is the highest data sequence number seen on the wire.

---

## 6. Final classification of run‑001

**B – VALID ZERO‑WINDOW OBSERVATION BUT INSUFFICIENT TO PROVE ACTIVE LIMITER**

The zero‑window is clearly observed, but the sender had already transmitted
the majority of the payload (high‑water reached its final value) before the
receiver’s pause, and no new sequence numbers appear after the window reopens.

---

## 7. Minimum change required for run‑002 (if classification B)

*Goal*: guarantee that after the receiver’s pause there is still pending
application data, so that new sequence numbers are generated only after the
window re‑opens.

**Proposed change (application‑level only):**
1. Reduce the per‑`send()` chunk size from 65 536 bytes to 4 096 bytes.
2. Insert a short `usleep(5000)` µs delay after each `send()` call.  This lets
   the kernel’s send buffer drain between sends, ensuring the buffer is empty
   when the receiver advertises a zero window.
3. Keep the total payload size (128 MiB) and the receiver‑side pause unchanged.

With these adjustments, a `send()` will block during the zero‑window, and a
subsequent `send()` after the window reopens will produce observable new
sequence‑space progress, satisfying the experiment’s requirement.

---

*End of report*
