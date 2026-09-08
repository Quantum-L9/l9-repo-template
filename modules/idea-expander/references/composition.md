# Composition and Ownership

## Position

```text
Raw / Developed Idea
        ↓
Idea Expander
        ↓
ExpandedIdeaDossierPacket
        ↓
expansion gate                       ideaos.expansion.gate_expansion
        ↓
ExpansionGateReceipt (READY)
        ↓
decision handoff                     ideaos.lifecycle.build_decision_node_input
        ↓
IdeaExpanderDecisionNodeInput v3
        ↓
idea-expander-decision-node
        ↓
GO | CONDITIONAL_GO | HOLD | NO_GO
        ↓
IdeaExecutionPacket / l9-idea-execute when authorized
```

The expansion gate and the decision handoff are mandatory stages, not
formalities: the decision node accepts only a v3 input, and the handoff
recomputes the gate rather than trusting a supplied receipt. A dossier cannot
be passed to the decision node directly.

## Idea Expander owns

- faithful center extraction;
- wide/deep opportunity expansion;
- compounding-loop discovery;
- persona/archetype decision effects during expansion;
- substrate-leverage assessment;
- candidate convergence/disposition;
- idea-pack hardening and Unknown surfacing;
- expanded-dossier handoff.

## Idea Expander does not own

- final investment/business decision;
- business-plan red team and polycognitive board aggregation;
- implementation planning;
- coding;
- repository birth;
- execution routing;
- production deployment.

## Compose, do not copy

Inside IdeaOS, treat the live protocols as authority:

- `protocols/01_DREAM_INVARIANT_WEDGE_PROOF.md`
- `protocols/02_WIDE_DEEP_RETURN_TO_CENTER.md`
- `protocols/04_PERSONA_ARCHETYPE_EVALUATION.md`
- `protocols/05_SUBSTRATE_LEVERAGE.md`
- `templates/DEEP_DOSSIER_INDEX.md`
- `templates/WIDE_DEEP_RETURN_TO_CENTER.md`

This module orchestrates those obligations and produces a validated handoff. It must not fork their doctrine into a second canonical brain.
