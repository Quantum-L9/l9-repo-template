# Changelog

## 11.4.0 — Lifecycle Complete

- promoted `idea-expander` into the canonical IdeaOS lifecycle
- added machine-readable `pipeline/IDEA_LIFECYCLE.yaml`
- added first-class `decision_handoff` runtime operation
- added `DecisionHandoffRequest`, `DecisionContext`, and `IdeaExpanderDecisionNodeInput v3` schemas
- bound decision input to the exact READY `ExpansionGateReceipt`
- enforced `receipt.input_digest == semantic_digest(expansion_packet)`
- hardened decision-node validator against stale/tampered post-gate dossiers
- added tamper regression fixture
- added lifecycle handoff unit tests
- updated expander and decision-node Skill contracts
- added canonical lifecycle and handoff architecture/protocol docs
- removed the conceptual trust-by-claim path from expand to decide

## 11.3.0 — Expansion Hardened

- added `idea-expander`
- added deterministic expansion gate
- added expanded dossier contracts and decision-node handoff doctrine
