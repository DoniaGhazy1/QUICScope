# Smoke‑test run directory

This directory was created automatically by the Cline AI to hold the artefacts
for a short (3 s) TCP‑CC‑001 instrumentation validation run.

Expected files after the experiment:
  sender_app_log.csv          – CSV of sender‑side events (raw timestamps from CLOCK_MONOTONIC_RAW)
  sender_tcpinfo_log.csv      – CSV of periodic TCP_INFO snapshots (also raw timestamps)
  bpf_events.log             – space‑separated output from the filtered bpftrace probe (timestamps from CLOCK_MONOTONIC)
  clock_offset_pre.txt        – raw_before, monotonic, raw_after, raw_mid, offset, uncertainty (ns)
  clock_offset_post.txt       – same format after the run
  sender_stderr.log           – any stderr produced by the sender binary
  probe_stderr.log            – any stderr from bpftrace (e.g. verifier messages)

The directory must remain empty before the run starts; the script below will
abort if any file already exists.