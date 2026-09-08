# Pipeline State Machine

Canonical lifecycle:

```text
CREATED
  -> EXPANDING
  -> EXPANSION_PACKET_EMITTED
  -> EXPANSION_GATE
  -> EXPANDED_READY
  -> DECISION_HANDOFF_BOUND
  -> DECIDING
  -> DECIDED
  -> PROMOTION_GATE
  -> EXECUTION_PACKET
  -> EXECUTION
```

A BLOCKED expansion gate cannot reach decision.
A decision handoff whose receipt does not bind the exact dossier cannot reach decision.
A HOLD or NO_GO decision cannot reach execution.
A CONDITIONAL_GO cannot execute until its named conditions are satisfied.
