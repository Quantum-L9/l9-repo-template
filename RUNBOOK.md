# IdeaOS Lifecycle Runbook

## 1. Create
Capture the idea and resolve the current Dream / Invariant / Wedge / Proof center under IdeaOS authority and source-lineage rules.

## 2. Expand
Invoke `modules/idea-expander/`.
Produce `ExpandedIdeaDossierPacket` and validate the package locally.

## 3. Gate expansion
Submit the exact packet to the IdeaOS runtime `expansion_gate` operation.
If BLOCKED, return to expansion. Do not proceed to decision.

## 4. Bind decision handoff
Submit the exact packet, its matching READY `ExpansionGateReceipt`, and `DecisionContext` to `decision_handoff`.
IdeaOS verifies the packet digest and emits `IdeaExpanderDecisionNodeInput v3`.

## 5. Decide
Invoke `modules/idea-expander-decision-node/` with only the v3 bound input.
The node independently rechecks the digest binding, then runs SWOT, business-plan synthesis, red-team refinement, and polycognitive adjudication.

## 6. Execute
Only GO or satisfied CONDITIONAL_GO outcomes may progress through existing promotion and `IdeaExecutionPacket` generation to `l9-idea-execute`.

## Failure rule
Never ask the decision node to trust an expansion packet merely because the packet claims READY. The receipt binds authority to exact bytes/semantics.
