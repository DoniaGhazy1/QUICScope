# Skill: Semantic Probe Localization

## Objective

Identify candidate implementation locations for observing a defined
transport-semantic event.

## Inputs

Required:

- semantic signal definition;
- relevant protocol/RFC semantics;
- target implementation;
- target implementation version/commit;
- source tree;
- available symbols/debug information.

## Rule

Search for behavior, not only names.

Do not assume that a function whose name resembles the target signal
implements the semantic transition.

## Procedure

### 1. Restate semantic event

Example:

    loss_declared

means:

    an outstanding packet becomes classified as lost according to the
    transport loss-detection algorithm.

### 2. Identify required state transition

Ask:

- What state exists before the event?
- What condition causes the transition?
- What state exists after it?
- What side effects should occur?

### 3. Consult protocol semantics

Identify the relevant RFC algorithm/condition.

### 4. Search source

Search for:

- relevant state fields;
- state mutation;
- algorithm conditions;
- callbacks;
- call graph;
- related functions.

Names are hints only.

### 5. Trace control flow

Determine:

    caller
      ↓
    decision
      ↓
    state mutation
      ↓
    side effects

### 6. Generate candidates

For each candidate provide:

    function:
    file:
    line:
    semantic rationale:
    arguments/state available:
    expected invocation frequency:
    potential false positives:
    potential false negatives:
    probe feasibility:

### 7. Rank

Return:

    candidate 1
    candidate 2
    candidate 3

Do not return a candidate as "correct."

Use:

    HIGH_CONFIDENCE_CANDIDATE

not:

    VERIFIED_HOOK

Verification belongs to the probe-validation skill.
