# Decision Node

The decision node consumes `IdeaExpanderDecisionNodeInput v3`, never an unbound expansion dossier.

Required chain:

```text
idea-expander
 -> ExpandedIdeaDossierPacket
 -> expansion_gate
 -> READY ExpansionGateReceipt
 -> decision_handoff
 -> IdeaExpanderDecisionNodeInput v3
 -> idea-expander-decision-node
```

The node independently verifies the receipt digest against the exact expansion packet before SWOT, business-plan synthesis, red-team refinement, or board adjudication.

Only this stage may emit GO, CONDITIONAL_GO, HOLD, or NO_GO.
