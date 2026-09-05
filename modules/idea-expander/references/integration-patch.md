# IdeaOS Integration Patch

## Add

```text
modules/idea-expander/
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
```

## Canonical pipeline

Update IdeaOS documentation/runtime routing so the semantic pipeline is explicitly:

```text
Spark / Developed Idea / Uploaded Pack
  -> Idea Expander
  -> ExpandedIdeaDossierPacket
  -> expansion gate            -> ExpansionGateReceipt (READY)
  -> decision handoff          -> IdeaExpanderDecisionNodeInput v3
  -> idea-expander-decision-node when decision evaluation is required
  -> IdeaDecisionPacket
  -> IdeaExecutionPacket
```

`pipeline/IDEA_LIFECYCLE.yaml` is the machine authority for this topology.

## Existing doctrine remains authoritative

The module consumes, rather than forks:

- `protocols/01_DREAM_INVARIANT_WEDGE_PROOF.md`
- `protocols/02_WIDE_DEEP_RETURN_TO_CENTER.md`
- `protocols/04_PERSONA_ARCHETYPE_EVALUATION.md`
- `protocols/05_SUBSTRATE_LEVERAGE.md`
- `templates/DEEP_DOSSIER_INDEX.md`

## Decision-node seam

`idea-expander-decision-node` accepts exactly one artifact: an
`IdeaExpanderDecisionNodeInput v3` carrying the expansion packet, its
`ExpansionGateReceipt` and the decision context. There is no backward-compatible
path that accepts a dossier directly — accepting one would be the gate bypass the
v3 seam exists to close.

The expander ends before business-plan/QA/red-team/polycognitive adjudication.

## Routing rule

Activate expansion when:
- user asks to develop/expand/refine an idea;
- an uploaded pack should be expanded rather than audited;
- blue-sky / wide-deep analysis is requested;
- a developed concept needs hardening before decision-node evaluation.

Skip expansion when:
- source is already a locked implementation specification and the user requests execution only;
- task is a bounded existing-repo implementation change;
- user explicitly requests decision-node-only evaluation of an already-expanded dossier.
