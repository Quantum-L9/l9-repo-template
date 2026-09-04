# IdeaOS 11.4 — Lifecycle Complete

IdeaOS now has an explicit, fail-closed idea lifecycle:

```text
create -> expand -> decide -> execute
```

The shorthand expands mechanically to:

```text
CREATE
  -> modules/idea-expander
  -> ExpandedIdeaDossierPacket
  -> IdeaOS expansion_gate
  -> ExpansionGateReceipt
  -> IdeaOS decision_handoff
  -> IdeaExpanderDecisionNodeInput v3
  -> modules/idea-expander-decision-node
  -> IdeaDecisionPacket
  -> promotion / execution packet
  -> l9-idea-execute
```

## What 11.4 closes

11.3 added the expander and deterministic expansion gate. 11.4 closes the remaining trust seam:

- `modules/idea-expander/` is a first-class IdeaOS module.
- the lifecycle contract explicitly routes idea development through it before decision.
- the decision node no longer trusts `decision_node_handoff.status: READY` by itself.
- it requires the runtime-issued `ExpansionGateReceipt`.
- the receipt's `input_digest` must equal the semantic digest of the exact dossier consumed.
- a dossier changed after validation is rejected.
- direct decision entry is permitted only with the exact validated dossier + matching READY receipt.

## Authority boundary

The expander discovers and converges. It does not decide.
The decision node adjudicates. It does not retroactively rewrite the expansion history.
Execution begins only from a valid downstream decision and promotion state.

See `pipeline/IDEA_LIFECYCLE.yaml` for the machine-readable topology.
