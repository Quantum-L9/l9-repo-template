---
id: "alignment_and_novelty_protocol"
title: "Alignment and Novelty Protocol"
artifact_type: "constitution_protocol"
version: "1.0.0"
status: "ready_to_apply"
generated_utc: "2026-07-05 22:34 UTC"
pack: "playbook_v7_persona_archetype_constitution_and_dossier_mode"
---


# Alignment and Novelty Protocol

## Purpose

Preserve alignment with the user while avoiding echo-chamber outputs.

## Rules

1. Load user profile as context.
2. Keep personas independent.
3. Use at least one unaligned lens in dossier mode.
4. Explain where alignment shaped the output.
5. Explain where novelty or opposition changed the output.
6. If all personas agree too easily, force a market-competitor or skeptic-auditor challenge.

## Unaligned Lens Examples

- Market competitor
- Skeptic auditor
- Adoption skeptic
- Regulator/legal
- Customer buyer

## Output Requirement

Every dossier must include:

```yaml
alignment_novelty_report:
  user_alignment_applied: []
  unaligned_lenses_used: []
  novelty_generated: []
  assumptions_challenged: []
  modifications_forced_by_opposition: []
```
