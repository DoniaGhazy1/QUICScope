# Skill: eBPF Transport Instrumentation

## Objective

Use external eBPF instrumentation to observe transport-semantic events
without modifying the target transport implementation.

## Principles

Prefer:

    semantic correctness

over:

    convenient hook names

Prefer probes that:

- expose required state;
- have stable semantics;
- minimize hot-path overhead;
- avoid duplicate counting.

## Before Instrumenting

Determine:

    target process
    binary
    build ID/version
    symbols
    debug information
    target function
    target semantic event

Confirm that the running binary corresponds to the source version used
during localization.

## Probe Design

For each probe document:

    semantic signal
    binary
    function/symbol
    probe type
    captured arguments
    captured fields
    filtering
    emitted event schema

## Event Schema

Prefer normalized output such as:

    timestamp
    pid
    connection_id
    signal
    value
    implementation
    hook

## Overhead

Instrumentation overhead must be measured.

Compare:

    baseline workload

against:

    instrumented workload

Use repeated runs.

Report:

    mean
    standard deviation
    relative overhead

Do not assume low event count means low overhead.

Hook location can influence transport timing even when the probe body is
small.

## Cleanup

Remove probes after experiments.

Confirm no instrumentation remains before subsequent baseline runs.
