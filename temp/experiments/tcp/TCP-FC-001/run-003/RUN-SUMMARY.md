# RUN‑003 – RAW EXECUTION SUMMARY
#
# **Purpose**: Measurement‑quality repeat of run‑002 with a larger tcpdump capture
# buffer.  The TCP workload (sender → receiver) was **unchanged**; only the capture
# configuration was altered.
#
# ---
#
# ## 1. Sender execution
#
# | Item | Value |
# |------|-------|
# | **Exit status** | `1` |
# | **Accepted‑byte total** | `0 bytes` |
# | **Event counts** | `error: 1` |
# | **Maximum `send()` duration** | `0 ns` (no successful send) |
#
# ## 2. Connection details
#
# *Four‑tuple* (client → server):
#
# ```
# 192.168.88.20:47072 → 192.168.88.21:5203
# ```
#
# No successful TCP handshake was observed – the connection attempt was
# refused by the receiver.
#
# ## 3. Capture statistics
#
# | Metric | Value |
# |--------|-------|
# | **Capture file size** | `134,555,250 bytes` |
# | **Packets captured** | `4102` |
# | **Packets received by filter** | `4102` |
# | **Packets dropped by kernel** | `0` |
#
# ### Packet‑type presence (from `tcpdump` analysis)
#
# | Packet type | Present? | Count |
# |------------|----------|-------|
# | SYN | Yes | `2` |
# | SYN‑ACK | Yes | `1` |
# | Data (payload) | Yes | `2 492` |
# | Receiver ACK (no payload) | Yes | `1 604` |
# | FIN | Yes | `2` |
# | RST | Yes | `1` |
#
# ## 4. Execution anomaly
#
# The sender failed to connect: `ConnectionRefusedError: [Errno 111] Connection refused`.
# This indicates that the receiver was not listening on the expected address/port at
# the moment the sender attempted to connect.
#
# ## 5. Confirmation
#
# - `RUN‑SUMMARY.md` created in `/home/rosa/experiments/tcp/TCP-FC-001/run-003/`
#
# ---
#
# *Document version: 1.0 – 2026‑10‑07*
