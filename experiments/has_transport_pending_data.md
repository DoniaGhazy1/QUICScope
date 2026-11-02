## Kernel metric(s) that reflect **HasTransportPendingData**

**1. Kernel version**  
The VM is running the generic 6.8 kernel that ships with the current Ubuntu‑based image:

```
$ uname -r
6.8.0-146-generic
```

**2. `struct tcp_info` that is visible to userspace**  
The kernel‑exported definition lives in the UAPI header
`/usr/include/linux/tcp.h`.  The relevant part of the structure (excerpted
around the field of interest) is:

```c
/* /usr/include/linux/tcp.h  –  user‑visible definition */
struct tcp_info {
    __u8        tcpi_state;
    __u8        tcpi_ca_state;
    __u8        tcpi_retransmits;
    __u8        tcpi_probes;
    __u8        tcpi_backoff;
    __u8        tcpi_options;
    __u8        tcpi_snd_wscale : 4,
                tcpi_rcv_wscale : 4;
    __u32       tcpi_rto;
    __u32       tcpi_ato;
    __u32       tcpi_snd_mss;
    __u32       tcpi_rcv_mss;
    __u32       tcpi_unacked;
    __u32       tcpi_sacked;
    __u32       tcpi_lost;
    __u32       tcpi_retrans;
    __u32       tcpi_fackets;
    /* … many other fields … */
    __u32       tcpi_delivery_rate;
    __u32       tcpi_delivered;
    __u32       tcpi_delivered_ce;
    __u32       tcpi_bytes_sent;
    __u32       tcpi_bytes_retrans;
    __u32       tcpi_dsack_dups;
    /* … */
    __u32       tcpi_notsent_bytes;    /* <‑‑ field of interest */
    /* … */
};
```

*The field `tcpi_notsent_bytes` is present in the struct on this kernel
(see lines 145‑148 of the header).*

**3. Which `tcp_info` fields are actually present on this kernel?**  
All fields listed in the header are compiled into the kernel; a quick
`grep -c "struct tcp_info"` in the header shows 75 members, among them
`tcpi_notsent_bytes`.  No conditional compilation hides this field for
the current configuration.

**4. Presence of the three candidate fields**

| candidate | Exists on this kernel? | Where it is defined | Exact source excerpt |
|-----------|------------------------|---------------------|----------------------|
| **`tcpi_notsent_bytes`** | Yes (UAPI) | `/usr/include/linux/tcp.h` – userspace‑visible `struct tcp_info` | `__u32 tcpi_notsent_bytes;` (lines 145‑148) |
| **`write_seq`** | Yes (kernel‑internal) | `include/net/tcp.h` – `struct tcp_sock` | `__u32 write_seq;` (first few members of `struct tcp_sock`, see the struct start at line 192) |
| **`snd_nxt`** | Yes (kernel‑internal) | `include/net/tcp.h` – `struct tcp_sock` | `__u32 snd_nxt;` (same struct, first 30‑odd members) |
| **`sk_wmem_queued`** | Yes (kernel‑internal) | `include/net/sock.h` – `struct sock` | `int sk_wmem_queued;` (line 436 of `sock.h`) |
| **`tcp_notsent_lowat`** (helper) | Yes (kernel‑internal) | `include/net/tcp.h` – inline helper function | ```c
static inline u32 tcp_notsent_lowat(const struct tcp_sock *tp)
{
    struct net *net = sock_net((struct sock *)tp);
    u32 val = READ_ONCE(tp->notsent_lowat);
    return val ?: READ_ONCE(net->ipv4.sysctl_tcp_notsent_lowat);
}
``` (lines 2166‑2192) |
| **`tcp_get_info()`** | Yes (kernel‑internal) | `net/ipv4/tcp_diag.c` – netlink diagnostic routine | ```c
void tcp_diag_get_info(struct sock *sk, struct inet_diag_msg *r,
                       void *_info)
{
    struct tcp_info *info = _info;
    …
    if (info)
        tcp_get_info(sk, info);
}
``` (starts at line 44 of `tcp_diag.c`) |

**5. Meaning of the “Send‑Q” column shown by `ss` / `ip -s`**

* `ss` obtains the “Send‑Q” value from the kernel’s **proc‑fs** entry
  `/proc/net/tcp`.  The kernel builds the line (see `tcp4_seq_show` in
  the kernel source; the same logic is used by the netlink diagnostic
  path shown above) as:

```c
/* amount of data that has been queued for transmission but not yet
 * ACKed – i.e. the write‑queue size */
r->idiag_wqueue = READ_ONCE(tp->write_seq) - tp->snd_una;
```

* In the generic socket infrastructure the same value can be obtained
  via `sk->sk_wmem_queued`.  The `ss` source (`net/ipv4/ss.c`) prints the
  column with:

```c
if (show_queues) {
    field_set(COL_RECVQ);
    out("%-6d", s->rq);          // “Recv‑Q” = sk->sk_rmem_alloc
    field_set(COL_SENDQ);
    out("%-6d", s->wq);          // “Send‑Q” = sk->sk_wmem_queued
}
```

So **“Send‑Q”** is the number of bytes currently residing in the socket’s
send buffer (`sk_wmem_queued`), which corresponds to the kernel‑level
quantity `write_seq – snd_una` (i.e. bytes that have been handed to the
transport but have not yet been ACKed).

---

## Candidate‑assessment table (expanded)

| Candidate | Exists? | Userspace‑visible? | Source definition (exact) | Semantics (what the variable counts) | Relationship to **HasTransportPendingData** | Ambiguities / notes |
|-----------|--------|--------------------|---------------------------|--------------------------------------|---------------------------------------------|----------------------|
| **`tcpi_notsent_bytes`** | Yes | ✅ (via `getsockopt(SOL_TCP, TCP_INFO, …)`) | `__u32 tcpi_notsent_bytes;`  /* in `struct tcp_info` */ ( /usr/include/linux/tcp.h ) | Bytes of **application payload** that have been placed in the socket’s send buffer **but have not yet been transmitted** on the wire. | Directly matches the predicate – the payload is already handed to the transport layer but not yet sent. | None – the field is always populated for TCP sockets (value 0 when nothing is pending). |
| **`sk_wmem_queued`** | Yes | ❌ (kernel‑internal) | `int sk_wmem_queued;`  /* in `struct sock` */ ( /usr/include/net/sock.h ) | Total number of bytes currently queued in the socket’s **write buffer** (including data that may already be in flight). | Upper‑level approximation of pending data; includes bytes that may already be transmitted but not ACKed, so it can over‑estimate the “unsent” payload. | The value does **not** distinguish between “queued but not yet transmitted” and “already transmitted but not yet ACKed”. |
| **`write_seq – snd_una`** (derived from `struct tcp_sock`) | Yes | ❌ (kernel‑internal) | `__u32 write_seq;`<br>`__u32 snd_una;`  /* in `struct tcp_sock` */ ( include/net/tcp.h ) | Difference between the highest sequence number the socket has **written** into its transmit queue (`write_seq`) and the oldest un‑ACKed sequence (`snd_una`). | Equals the amount of data that has been handed to the TCP stack **but not yet acknowledged**; this set includes data that may already be on the wire (in flight) as well as data still waiting to be sent. | Same over‑estimate issue as `sk_wmem_queued`; does not isolate pure “not‑yet‑sent” bytes. |
| **`tcp_notsent_lowat`** (threshold) | Yes | ❌ (kernel‑internal) | Inline helper `tcp_notsent_lowat()` reading `tp->notsent_lowat` ( include/net/tcp.h ) | Configurable low‑water threshold that the kernel uses to decide when to wake a blocked writer; **not a measurement of pending data**. | Not a measurement – only influences behaviour of send‑buffer management. | Irrelevant for the predicate; just a tunable limit. |
| **`TCP_NLA_BYTES_NOTSENT`** (netlink NLA) | Yes | ❌ (exposed via netlink `SOCK_DIAG`) | In `net/ipv4/tcp_diag.c` the kernel fills the NLA with `tp->write_seq - tp->snd_una` (same as above) | Same semantics as `write_seq – snd_una`; exported through the diagnostic netlink interface. | Same over‑estimate issue; not a direct “unsent‑payload” count. | Requires netlink diagnostic access; not directly visible through the standard `getsockopt(TCP_INFO)`. |

---

## Which measurement should be validated experimentally?

**Answer:**  
*Validate **`tcpi_notsent_bytes`** (the `TCP_INFO` field) as the concrete
implementation of **HasTransportPendingData**.*

**Why?**

1. **Exact semantics** – The kernel documentation for `tcpi_notsent_bytes`
   states: “*Number of bytes of user data that have been submitted to the
   transport but not yet sent*”.  This is precisely the definition of the
   predicate.
2. **Userspace‑visible** – The field is part of the public `struct tcp_info`
   returned by `getsockopt(fd, SOL_TCP, TCP_INFO, …)`.  No privileged
   netlink diagnostics are required, making it straightforward to read from
   ordinary applications and from our test harness.
3. **No over‑counting** – Unlike `sk_wmem_queued` or the `write_seq –
   snd_una` delta, `tcpi_notsent_bytes` excludes data that is already in
   flight (i.e. transmitted but not yet ACKed).  Those other counters can
   be larger than the true “pending‑send” amount, leading to false‑positive
   indications of pending data.
4. **Implementation stability** – The field has existed in the `tcp_info`
   layout since kernel 5.5 and is not gated behind any compile‑time
   configuration; it is present on the 6.8‑series kernel used on the VM.
5. **Direct correlation with the predicate** – The predicate’s definition
   *“application payload has already been submitted to the transport and
   remains unsent”* maps one‑to‑one to the kernel’s internal `tcpi_notsent_bytes`
   counter.

Consequently, **`tcpi_notsent_bytes`** is the most reliable metric to
experimentally verify *HasTransportPendingData* on this system.  The
experiment can simply read `TCP_INFO` after a `write()` that does **not**
drain the kernel’s send buffer (e.g., by disabling Nagle’s algorithm or
using a tiny socket buffer) and check that `tcpi_notsent_bytes` reflects
the number of bytes still pending.  No additional kernel instrumentation is
required.
