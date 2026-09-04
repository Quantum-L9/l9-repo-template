# Expansion-to-Decision Handoff

The expansion-to-decision seam is fail-closed.

Required artifacts:
1. `ExpandedIdeaDossierPacket`
2. matching `ExpansionGateReceipt`
3. `DecisionContext`

IdeaOS runtime compiles those into `IdeaExpanderDecisionNodeInput v3` only when:
- gate status is `READY`;
- gate blockers are empty;
- decision handoff is allowed;
- idea IDs match;
- the gate receipt digest equals the semantic digest of the exact dossier;
- the expander itself did not usurp final decision authority.

The decision node validates the same binding independently before reasoning.

This is deliberate defense in depth. A stale or modified dossier cannot inherit an earlier READY receipt.
