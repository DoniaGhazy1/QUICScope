# State‑Combination Analysis of BPF Observations

* Total BPF events processed: **165756**

## Joint D/F/C predicate distribution

```D=FALSE, F=TRUE, C=TRUE: 300
D=TRUE, F=FALSE, C=TRUE: 22607
D=TRUE, F=TRUE, C=FALSE: 5298
D=TRUE, F=TRUE, C=TRUE: 137551
```

## Semantic state counts (per frozen definition)

```APP_LIMITED: 300
CC_LIMITED: 5298
FC_LIMITED: 22607
READY: 137551
```

## R distribution within each state

```APP_LIMITED: R_TRUE=0, R_FALSE=300
CC_LIMITED: R_TRUE=54, R_FALSE=5244
FC_LIMITED: R_TRUE=0, R_FALSE=22607
READY: R_TRUE=96, R_FALSE=137455
```

## Most frequent state transitions

```READY → FC_LIMITED: 5716
FC_LIMITED → READY: 5716
READY → CC_LIMITED: 888
CC_LIMITED → READY: 888
READY → APP_LIMITED: 265
APP_LIMITED → READY: 265
```

## Example transitions (timestamps and raw predicates)

### READY → FC_LIMITED
* **Prev** ts=1892778079343 D=TRUE F=TRUE C=TRUE R=FALSE
* **Next** ts=1892778086319 D=TRUE F=FALSE C=TRUE R=FALSE

### READY → CC_LIMITED
* **Prev** ts=1892743587755 D=TRUE F=TRUE C=TRUE R=FALSE
* **Next** ts=1892743594335 D=TRUE F=TRUE C=FALSE R=FALSE

### FC_LIMITED → CC_LIMITED: NOT OBSERVED

### CC_LIMITED → FC_LIMITED: NOT OBSERVED

## Unsupported/ambiguous combinations

_None – every BPF event maps to a defined state._
