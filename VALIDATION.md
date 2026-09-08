# Validation

Run from pack root. `jsonschema` and `referencing` are required.

```bash
python scripts/validate_ideaos_114_pack.py
python -m unittest discover -s tests -p 'test_*.py'
python modules/idea-expander/scripts/validate_expansion_package.py tests/expansion_packet.ready.json
python modules/idea-expander-decision-node/scripts/validate_decision_input.py modules/idea-expander-decision-node/tests/node-input.ready.json
python modules/idea-expander-decision-node/scripts/validate_decision_package.py modules/idea-expander-decision-node/tests/decision-package.valid.json
```

## Regressions that MUST fail

A gate is only proven by what it refuses. Each command below exits non-zero, and
each corresponds to a bypass that was reproduced against 11.4.0.

```bash
# dossier edited after the gate issued its receipt
python modules/idea-expander-decision-node/scripts/validate_decision_input.py \
  modules/idea-expander-decision-node/tests/node-input.tampered.json

# a hand-written READY receipt, digest-correct, for a packet the gate BLOCKS
python modules/idea-expander-decision-node/scripts/validate_decision_input.py \
  modules/idea-expander-decision-node/tests/node-input.forged-receipt.json
```

The first proves a dossier cannot be modified after the expansion gate and still
inherit its READY authority. The second proves the reverse and stronger claim:
authority cannot be manufactured at all, because the handoff recomputes the gate
rather than reading the receipt's own word for it.

`tests/test_decision_package.py` carries the same discipline for the decision
package — an unknown decision value, an integer board vote, a GO over an
unresolved critical finding, an unconditional GO over a conditioned one, a
CONDITIONAL_GO with no executable gate, a condition with no trigger, and a
minority vote with an empty dissent register are each rejected.

## Installer

The installer refuses a target that is not the bound baseline. Verifying that it
refuses is part of validation, not an optional extra:

```bash
python scripts/apply_lifecycle_to_ideaos.py /path/to/some/other/checkout --dry-run
```

This exits non-zero unless HEAD is the commit named in `TRACEABILITY.yaml` and the
worktree is clean. `--allow-head <sha>` names a different commit deliberately;
`--force` overrides admission entirely and prints what it overrode.
