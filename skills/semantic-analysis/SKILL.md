# Skill: Semantic Transport Analysis

## Input

Raw experiment artifacts.

## Output

An evidence-based semantic classification.

## Procedure

For every candidate diagnosis construct an evidence table:

| Claim | Evidence | Source | Supports? |
|------|----------|--------|-----------|

Sources:

    WIRE_DIRECT
    WIRE_INFERRED
    ENDPOINT
    CONTROLLED_GROUND_TRUTH

## Congestion-Control-Limited

Check:

1. Is application data available?
2. Is receiver flow control non-binding?
3. Is congestion-control/recovery state preventing additional sends?

Do not infer (3) solely from throughput.

## Flow-Control-Limited

Check:

1. Is sender data available?
2. Is receiver credit/window binding?
3. Is congestion control not the primary limitation?

## Application-Limited

Check:

1. Does transport have sending opportunity?
2. Is congestion control non-binding?
3. Is flow control non-binding?
4. Does application lack data?

## Classification

Return:

    classification:
    confidence:
    supporting evidence:
    contradicting evidence:
    missing evidence:

It is acceptable to return:

    INSUFFICIENT_EVIDENCE

This is preferable to unsupported classification.
