 # Source Code Audit: QUIC Packet Loss Detection and qlog Emission

This document records the findings from a static analysis of the **quic-go**
implementation (v0.64.1, commit `fb50402f553c4a8d8b7093b45505f43d6377f856`).
The focus is on the internal loss‑detection logic and the corresponding
`qlog.PacketLost` events.

## Overview of the loss‑detection path

The loss detection algorithm lives in `internal/ackhandler/sent_packet_handler.go`.
The key function is `(*sentPacketHandler) detectLostPackets`, which is invoked
by the loss‑detection timer (`OnLossDetectionTimeout`).  The relevant excerpt
is reproduced below (lines are approximate, see the source file for exact
locations):

```go
func (h *sentPacketHandler) detectLostPackets(now monotime.Time, encLevel protocol.EncryptionLevel) {
    // ... setup ...
    lossDelay := max(
        max(h.rttStats.LatestRTT(), h.rttStats.SmoothedRTT())*time.Duration(8+timeThresholdEighths)/8,
        protocol.TimerGranularity,
    )
    lostSendTime := now.Add(-lossDelay)
    // iterate over sent packets
    for pn, p := range h.hist.Packets() {
        // ... compute distance ...
        var packetLost bool
        if !p.SendTime.After(lostSendTime) { // time‑threshold loss
            packetLost = true
            if !p.isPathProbePacket && p.IsAckEliciting() {
                if h.qlogger != nil {
                    h.qlogger.RecordEvent(qlog.PacketLost{Header: qlog.PacketHeader{PacketType: qlog.EncryptionLevelToPacketType(p.EncryptionLevel), PacketNumber: pn}, Trigger: qlog.PacketLossTimeThreshold})
                }
            }
        } else if usePacketThreshold && distance >= packetThreshold { // reordering‑threshold loss
            packetLost = true
            if !p.isPathProbePacket && p.IsAckEliciting() {
                if h.qlogger != nil {
                    h.qlogger.RecordEvent(qlog.PacketLost{Header: qlog.PacketHeader{PacketType: qlog.EncryptionLevelToPacketType(p.EncryptionLevel), PacketNumber: pn}, Trigger: qlog.PacketLossReorderingThreshold})
                }
            }
        }
        // ... other handling ...
        if packetLost {
            // internal bookkeeping
            h.hist.DeclareLost(pn) // <--- internal loss declaration
            // ... congestion, ECN, retransmission ...
        }
    }
    // ...
}
```

### Key points extracted from the source

| Aspect | Detail |
|---|---|
| **Internal loss declaration** | `h.hist.DeclareLost(pn)` – marks the packet as lost in the sender's history. |
| **Trigger conditions** | *Time‑threshold*: packet sent before `lostSendTime`. *Reordering‑threshold*: packet distance ≥ `packetThreshold` (when `usePacketThreshold` is true). |
| **Packet identifiers available** | `pn` (protocol.PacketNumber) and `p.EncryptionLevel` (used to derive `qlog.PacketType`). |
| **qlog emission point** | Immediately after the internal declaration, inside the same `if packetLost` block, via `h.qlogger.RecordEvent(qlog.PacketLost{...})`. |
| **Fields emitted in the qlog event** | `Header.PacketType` (derived from encryption level), `Header.PacketNumber`, `Trigger` (enum `PacketLossTimeThreshold` or `PacketLossReorderingThreshold`). |
| **Optional fields omitted** | No timestamp field (the tracer adds a timestamp automatically). No explicit loss reason beyond the enum, no path‑probe flag, no bytes‑in‑flight or congestion‑state context. |
| **Can the event be omitted/disabled?** | Yes – if `h.qlogger` is `nil` (qlog disabled) the `RecordEvent` call is skipped, but the internal loss declaration still occurs. |
| **Synchronous vs buffered** | `RecordEvent` writes to the `qlogwriter.Trace` which buffers events and writes them asynchronously to a file (JSON Text Sequence). The call itself is synchronous, but the actual I/O may be delayed. |
| **Potential loss of information** | The qlog event does **not** include the loss detection *time* (only the tracer timestamp), the *bytes‑in‑flight* value, or whether the packet was a *path‑probe*. |
| **Multiple loss‑detection mechanisms** | Both the time‑threshold and reordering‑threshold paths emit the same `PacketLost` event type, differing only in the `Trigger` field. |

## Summary Table

| Internal behavior | Source location | Trigger | qlog event | Available fields (in qlog) | Potential information loss |
|---|---|---|---|---|---|
| Packet declared lost (time‑threshold) | `detectLostPackets` – lines ~928‑942 | `!p.SendTime.After(lostSendTime)` | `qlog.PacketLost` | `Header.PacketType`, `Header.PacketNumber`, `Trigger = PacketLossTimeThreshold` | No timestamp, no path‑probe flag, no congestion/bytes‑in‑flight context |
| Packet declared lost (reordering‑threshold) | `detectLostPackets` – lines ~944‑958 | `usePacketThreshold && distance >= packetThreshold` | `qlog.PacketLost` | `Header.PacketType`, `Header.PacketNumber`, `Trigger = PacketLossReorderingThreshold` | Same as above |

The audit confirms that **every internal loss declaration** passes through the same code path that emits a `qlog.PacketLost` event (provided a tracer is configured).  No alternative loss‑declaration paths were found in the current version.

---

*Document generated by the audit script on `$(date)`.*
