# Canonical Idea Lifecycle

IdeaOS 11.4 makes the idea lifecycle explicit and mechanically guarded:

```text
CREATE
  |
  v
EXPAND  -> modules/idea-expander
  |
  v
ExpandedIdeaDossierPacket
  |
  v
EXPANSION GATE
  |
  v
ExpansionGateReceipt
  |
  | digest binds the exact dossier
  v
DECISION HANDOFF
  |
  v
IdeaExpanderDecisionNodeInput v3
  |
  v
DECIDE -> modules/idea-expander-decision-node
  |
  v
IdeaDecisionPacket
  |
  v
EXECUTE -> IdeaExecutionPacket -> l9-idea-execute
```

## Critical invariant

The decision node may not trust the dossier's self-declared `READY` state.

It must receive the runtime-issued `ExpansionGateReceipt`, and:

```text
ExpansionGateReceipt.input_digest
== semantic_digest(ExpandedIdeaDossierPacket)
```

A dossier mutation after validation therefore invalidates the handoff.

## Authority

- `idea-expander` owns creative expansion and return-to-center convergence.
- `expansion_gate` owns deterministic expansion completeness/authority validation.
- `decision_handoff` owns exact artifact binding.
- `idea-expander-decision-node` alone owns GO / CONDITIONAL_GO / HOLD / NO_GO adjudication.
- execution occurs only from a valid downstream decision packet and existing promotion gates.

## Direct-entry rule

An already-expanded dossier may enter at the decision boundary only if accompanied by its exact matching READY gate receipt. There is no trust-by-claim bypass.
