---
name: idea-expander-decision-node
description: Evaluate an IdeaOS Expanded Idea Dossier after creative expansion and before execution authorization. Use when a validated idea-expander handoff must undergo three-perspective SWOT, business-plan synthesis, red-team refinement, and independent polycognitive board adjudication to produce GO, CONDITIONAL_GO, HOLD, or NO_GO with evidence-linked conditions. Do not use to perform the upstream expansion itself or to create implementation code.
---

# Idea Expander Decision Node

Convert a validated expanded dossier into an evidence-linked, condition-bearing decision.

## Authority

1. Current user intent and locked constraints.
2. Validated `idea-expander` handoff and source authority.
3. Verified external evidence and current L9 capability evidence.
4. This node's evaluation contracts.
5. `Unknown` rather than invention.

Read `references/node-operating-contract.md` before adjudication.

## Required upstream contract

Require the exact `expansion_packet.json` produced by `idea-expander` together with its matching `ExpansionGateReceipt`. The node input MUST be `ideaos.decision-node-input/v3` (`IdeaExpanderDecisionNodeInput v3`); its receipt `input_digest` MUST equal the semantic digest of the dossier being consumed. Reject a handoff that:

- lacks Dream / Invariant / Wedge / Proof;
- hides material Unknowns;
- omits candidate dispositions;
- contains a final GO/HOLD/NO_GO decision authored by the expander;
- is marked `BLOCKED` by the expansion gate;
- omits the ExpansionGateReceipt;
- has an `idea_id` mismatch;
- has a gate-receipt digest that does not match the exact dossier;
- was modified after expansion validation.

## Workflow

1. Validate the node input with `scripts/validate_decision_input.py`.
2. Run the three mandatory perspectives using `references/three-perspective-swot.md`.
3. Build the unified feasibility and leverage register.
4. Produce the business-plan handoff using `references/business-plan-handoff.md`.
5. Red-team the plan using `references/red-team-protocol.md`.
6. Refine only to address verified findings; do not erase dissent or uncertainty.
7. Convene the independent board using `references/polycognitive-board.md`.
8. Aggregate votes without allowing an average score to hide a fatal blocker.
9. Emit `decision_package.json` matching `schemas/decision-output.schema.json`.
10. Validate with `scripts/validate_decision_package.py`.

## Mandatory perspectives

- **Autonomous deployability**: can authorized agents and L9 build, operate, validate, observe, and improve it safely?
- **Marketability / saleability**: can a defined customer understand, trust, acquire, use, and retain it?
- **Profitability / economic resilience**: can it produce attractive cash economics and defensible compounding value?

## Decision law

- `GO`: issue downstream execution authorization.
- `CONDITIONAL_GO`: issue authorization only with named proof gates, owners, triggers, and failure consequences.
- `HOLD`: no execution authorization; issue evidence-acquisition / repair plan.
- `NO_GO`: stop; preserve resurrection conditions if any.

Unknown evidence never becomes confidence by rhetoric.

## Resources

- `references/node-operating-contract.md`
- `references/three-perspective-swot.md`
- `references/business-plan-handoff.md`
- `references/red-team-protocol.md`
- `references/polycognitive-board.md`
- `schemas/node-input.schema.json`
- `schemas/decision-output.schema.json`
- `scripts/validate_decision_input.py`
- `scripts/validate_decision_package.py`
