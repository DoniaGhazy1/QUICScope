# TCP Flow‑Control Reconstruction Debug – run‑001

## Handshake information

* Negotiated window‑scale = 7
* Negotiated MSS = 1460

## First event where passive usable credit becomes negative

No negative credit discovered – this contradicts the earlier quantitative file.

## Zero‑window advertisement snapshots

* First zero‑window ACK (57 total):
* ts=1791402958.219462, ack=9846785, raw_win=0, scaled_win=0, snd_nxt=128546089, snd_una_before=9846401, snd_una_after=9846785
* Middle zero‑window ACK:
* ts=1791402958.287326, ack=28596481, raw_win=0, scaled_win=0, snd_nxt=128546089, snd_una_before=28466817, snd_una_after=28596481
* Last zero‑window ACK:
* ts=1791402958.326685, ack=122429145, raw_win=0, scaled_win=0, snd_nxt=128546089, snd_una_before=122295769, snd_una_after=122429145

## First positive‑window update after zero‑window period

* Timestamp                 : 1791402958.326701
* ACK value                 : 122429145
* Raw Window                : 1238
* Scaled Window             : 158464

## Direct advertised right‑edge (ACK+scaled_window) vs snd_nxt

* No case where ACK+scaled_window fell below snd_nxt – direct right‑edge stays >= snd_nxt.

## Sender payload‑size distribution (possible TSO/GSO)

* Minimum payload length   : 376
* Median payload length    : 39096.0
* Maximum payload length   : 65160
* Packets with length > MSS (1460) : 2782
* Example large packet length : 7240

## Window‑scale verification (raw → scaled)

* ts=1791402957.962471, raw_win=623, scaled_win=79744
* ts=1791402958.280395, raw_win=1535, scaled_win=196480
* ts=1791402958.297839, raw_win=1535, scaled_win=196480
* ts=1791402958.329016, raw_win=1292, scaled_win=165376

## Credit computation summary

* Minimum stateful credit (snd_una+snd_wnd‑snd_nxt) : 0
* Zero‑credit observed (stateful) : yes

---
*This file is generated automatically for debugging purposes.*
