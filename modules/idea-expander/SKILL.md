---
name: idea-expander
description: Expand and harden a raw or developed idea into an IdeaOS-native deep dossier before decision-node evaluation. Use when an idea needs wide/deep opportunity expansion, Dream-Invariant-Wedge-Proof refinement, persona/archetype effects, substrate leverage, compounding loops, candidate convergence, explicit Unknowns, and a validated handoff to the idea-expander-decision-node. Do not use for go/no-go adjudication, implementation planning, repository creation, or execution routing.
---

# Idea Expander

Turn an idea into a stronger, focused, evidence-aware dossier without replacing it with an unrelated platform fantasy.

## Authority

1. Explicit current user intent and locked constraints.
2. Source pack authority/supersession rules.
3. Current IdeaOS doctrine for Dream/Invariant/Wedge/Proof, Wide/Deep/Return-to-Center, persona/archetype evaluation, substrate leverage, evidence/Unknown handling, and deep-dossier structure.
4. This module's expansion and handoff contracts.
5. `Unknown` rather than invention.

Read `references/composition.md` before expanding. Read `references/output-contract.md` before emitting the final dossier.

## Workflow

1. **Bind the source.** Inventory the supplied idea/pack, separate locked facts from proposals, hypotheses, Unknowns, deferred/rejected material, and preserve explicit supersession.
2. **Extract the center.** Resolve Dream, Invariant, Wedge, Proof, customer/beneficiary, economic thesis, constraints, and anti-goals. Do not improve yet.
3. **Expand wide.** Explore adjacent customers, use cases, partners, channels, geographies, business models, wedges, proof environments, and commercialization paths that could materially improve the idea.
4. **Expand deep.** Explore hidden capability, proprietary data/evidence, reusable substrate, learning loops, network effects, standards, ecosystem leverage, defensibility, switching cost, option value, and downstream strategic value.
5. **Apply independent lenses.** Use only personas/archetypes that can change the decision. Preserve at least one skeptic/opposition lens for material ideas. Record the concrete modification caused by each lens.
6. **Find compounding loops.** Identify loops where usage or proof improves data, learning, distribution, economics, trust, switching cost, or strategic option value.
7. **Return to center.** Give every candidate exactly one disposition: `integrate_now`, `sequence_later`, `preserve_option`, or `discard`. The revised center must be more powerful but still focused and executable.
8. **Harden the pack.** Surface contradictions, hidden dependencies, proof gaps, capture risks, overreach, ownership ambiguity, and material Unknowns. Do not silently convert them into confidence.
9. **Emit the dossier.** Produce the adaptive deep-dossier outputs in `references/output-contract.md` and a machine-readable `expansion_packet.json` matching `references/expansion-packet.schema.json`.
10. **Validate.** Run `python scripts/validate_expansion_package.py <expansion_packet.json>`. Fix deterministic failures before handoff.
11. **Gate.** Pass the exact `expansion_packet.json` through the IdeaOS `expansion_gate`; retain the resulting `ExpansionGateReceipt`.
12. **Bind handoff.** Use the IdeaOS `decision_handoff` operation to bind the exact packet + matching READY gate receipt + decision context into `IdeaExpanderDecisionNodeInput v3`.
13. **Handoff.** Pass only that validated input to `idea-expander-decision-node`. Do not make the final GO/HOLD/NO_GO decision here.

## Expansion rules

- Expansion is opportunity discovery, not source-plan auditing.
- Preserve the original invariant even when the revised business surface grows.
- Prefer a stronger wedge over a bigger vision.
- Separate direct commercial value from substrate/platform value.
- Treat a powerful substrate as leverage, not permission to avoid proving demand.
- Distinguish `VERIFIED`, `SUPPORTED_INFERENCE`, `HYPOTHESIS`, and `UNKNOWN` evidence states.
- Do not force every attractive branch into the revised center.
- Preserve options explicitly when they are valuable but premature.
- Reject branches that require changing the identity of the idea.
- When the idea already contains extensive expansion work, consolidate and sharpen it rather than adding decorative branches.

## Failure conditions

Fail the handoff when:

- Dream/Invariant/Wedge/Proof is missing or contradictory;
- candidate dispositions are absent;
- a material Unknown is presented as fact;
- wide/deep expansion merely mirrors the source;
- the revised center absorbs every attractive branch;
- an execution plan is emitted instead of an idea dossier;
- final investment/business GO/NO_GO judgment is made here.

## Resources

- `references/composition.md` - IdeaOS ownership and upstream/downstream seam.
- `references/expansion-protocol.md` - wide/deep lenses, compounding loops, and convergence rules.
- `references/output-contract.md` - required dossier and handoff outputs.
- `references/expansion-packet.schema.json` - deterministic machine contract.
- `references/integration-patch.md` - exact IdeaOS module placement and wiring.
- `scripts/validate_expansion_package.py` - package validator.
