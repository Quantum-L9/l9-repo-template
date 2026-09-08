# Output Contract

## Human dossier

Always include:

1. Executive summary
2. Source inventory / authority when sources exist
3. Original center: Dream / Invariant / Wedge / Proof
4. Wide discoveries
5. Deep discoveries
6. Compounding loops
7. Persona/archetype decision effects
8. Substrate assessment when material
9. Candidate disposition table
10. Revised center
11. Evidence / contradictions / Unknowns
12. Required pack modifications
13. Downstream decision-node handoff
14. Validation / manifest

## Machine output

Emit `expansion_packet.json` with:

- `idea_id`
- `source_refs`
- `original_center`
- `wide_discoveries`
- `deep_discoveries`
- `compounding_loops`
- `persona_effects`
- `substrate_assessment`
- `candidate_dispositions`
- `revised_center`
- `evidence_register`
- `unknowns`
- `modifications`
- `decision_node_handoff`

## Handoff rule

The decision node receives the **revised center plus the full evidence/Unknown surface**, not only the attractive discoveries.

The expander must not emit `GO`, `CONDITIONAL_GO`, `HOLD`, or `NO_GO` as its own final decision.
