# Validation

Run from pack root:

```bash
python scripts/validate_ideaos_114_pack.py
python -m unittest discover -s tests -p 'test_*.py'
python modules/idea-expander/scripts/validate_expansion_package.py tests/expansion_packet.ready.json
python modules/idea-expander-decision-node/scripts/validate_decision_input.py modules/idea-expander-decision-node/tests/node-input.ready.json
```

Tamper regression MUST fail:

```bash
python modules/idea-expander-decision-node/scripts/validate_decision_input.py modules/idea-expander-decision-node/tests/node-input.tampered.json
```

The failure is expected and proves a dossier cannot be modified after the expansion gate and still inherit its READY authority.
