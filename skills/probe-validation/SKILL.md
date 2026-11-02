# Skill: Probe Validation

## Objective

Determine whether a candidate probe faithfully observes its intended
semantic event.

## Principle

Probe output is not ground truth.

Validation must use independent evidence whenever possible.

## Validation Questions

### Precision

When the probe fires, did the semantic event actually occur?

### Recall

Did every known semantic event cause the probe to fire?

### Multiplicity

Does one semantic event produce exactly the expected number of probe
events?

### Ordering

Does the probe fire at the correct stage of the state transition?

### Side Effects

Does instrumentation perturb transport behavior?

---

## Controlled Scenario

Construct a workload where expected events can be independently
determined.

Record:

    expected event count
    observed probe count

Compute:

    absolute error
    relative error

Where event matching is available also determine:

    true positives
    false positives
    false negatives

---

## Probe Acceptance

A probe becomes VALIDATED only when:

1. semantic correspondence is demonstrated;
2. false positives are acceptably controlled;
3. false negatives are acceptably controlled;
4. instrumentation overhead is measured;
5. results are reproducible.

Otherwise retain status:

    CANDIDATE
