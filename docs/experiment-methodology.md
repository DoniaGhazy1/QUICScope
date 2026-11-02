# Experiment Methodology

## Rule

Every experiment must answer a specific hypothesis.

Do not begin by collecting arbitrary metrics.

---

## Experiment Template

### Question

What transport behavior are we testing?

### Hypothesis

What should happen?

### Controlled Variable

What condition are we intentionally changing?

### Independent Ground Truth

How do we know the condition actually occurred?

### Endpoint Evidence

What endpoint signals should change?

### Wire Evidence

What packet-level observations should change?

### Expected Diagnosis

What semantic state should the evidence support?

### Falsification

What observation would contradict the hypothesis?

---

# Experiment Lifecycle

## 1. Record baseline state

Capture:

    hostname
    uname -a
    ip addr
    ip route
    ethtool
    tc qdisc
    sysctl congestion control
    git commit

## 2. Apply controlled condition

Examples:

    bandwidth limit
    delay
    packet loss
    receiver limitation
    application pacing

Record exact commands.

## 3. Verify condition

Never assume tc or another configuration command had the intended
effect.

Inspect the resulting configuration.

## 4. Start packet capture

Capture the experiment interface.

## 5. Start endpoint telemetry

Collect required endpoint signals.

## 6. Run workload

Record exact workload command.

## 7. Stop collectors

Preserve raw outputs.

## 8. Analyze

Separate observations from interpretations.

## 9. Restore baseline

Remove temporary impairment.

## 10. Verify restoration

Confirm the system returned to its initial configuration.
