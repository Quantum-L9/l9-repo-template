# IdeaOS 11.4.1 Validation Report

Every block below is captured output from the command shown, run from pack root.
Where a claim is inherited from 11.4.0 rather than reproduced here, it says so.

## Pack topology and authority-chain validator

```text
$ python scripts/validate_ideaos_114_pack.py
PASS
IdeaOS 11.4 lifecycle topology and exact expansion-to-decision binding are present
```

## Lifecycle unit tests

```text
$ python -m unittest discover -s tests -p 'test_*.py'
......................
----------------------------------------------------------------------
Ran 22 tests in 1.906s

OK
```

## Idea Expander package validator

```text
$ python modules/idea-expander/scripts/validate_expansion_package.py tests/expansion_packet.ready.json
PASS
```

## Decision-node bound input validator

```text
$ python modules/idea-expander-decision-node/scripts/validate_decision_input.py modules/idea-expander-decision-node/tests/node-input.ready.json
PASS
```

## Decision package validator

```text
$ python modules/idea-expander-decision-node/scripts/validate_decision_package.py modules/idea-expander-decision-node/tests/decision-package.valid.json
PASS
```

## Regressions that must fail

### Tamper after the gate

```text
$ python modules/idea-expander-decision-node/scripts/validate_decision_input.py modules/idea-expander-decision-node/tests/node-input.tampered.json
FAIL: expansion packet digest does not match ExpansionGateReceipt; the dossier was changed after validation
```

Proves a dossier changed after the expansion gate cannot reuse the earlier READY receipt.

### Forged gate receipt

A hand-written READY receipt whose digest correctly matches a packet the real gate BLOCKS.
Nothing was edited after validation, so digest binding alone accepts it; only recomputing
the gate does not.

```text
$ python modules/idea-expander-decision-node/scripts/validate_decision_input.py modules/idea-expander-decision-node/tests/node-input.forged-receipt.json
FAIL: expansion gate does not authorize this packet; the supplied receipt was not issued by the gate. Recomputed blockers: DISPOSITION_COVERAGE_MISMATCH
```

Proves gate authority cannot be manufactured, not merely that it cannot be reused.

## Installer admission

A synthetic tree carrying the three files 11.4.0's installer checked for.

```text
$ python scripts/apply_lifecycle_to_ideaos.py /tmp/synthetic-checkout --dry-run
Refusing to apply:
- /tmp/synthetic-checkout is not a git repository (git rev-parse HEAD failed)
Pass --force to override.
```

11.4.0 admitted this tree and would have proceeded to `rmtree` its module directories.

## Pack integrity

`MANIFEST.json` covers every payload file except itself and `SHA256SUMS.txt`;
`SHA256SUMS.txt` covers everything except itself, including `MANIFEST.json`.
Both are regenerated after this report is written, since the report is itself a
covered file — so verify them against the shipped tree rather than taking the
counts below on trust:

```text
$ python -c "import hashlib,json;from pathlib import Path;P=Path('.');m=json.loads((P/'MANIFEST.json').read_text());print(sum(1 for e in m['files'] if hashlib.sha256((P/e['path']).read_bytes()).hexdigest()==e['sha256']),'/',len(m['files']))"
102 / 102
```

## Skill package validation

11.4.0 reported PASS from the official Skill packager for both embedded Skills but
shipped no packager receipt. That claim is **inherited and unverified here** — this
pack contains no evidence for it either way, and it should not be read as validated.

## Result

**PASS** for the fail-closed authority chain, exact receipt/digest binding, gate
recomputation, decision-package contract enforcement, baseline-bound installer
admission, and pack integrity.

Not claimed:

- unchanged IdeaOS 11.2 baseline surfaces are not revalidated by this pack;
- the decision-node-output to canonical `IdeaDecisionPacket` mapping is not
  evidenced here and may be baseline-owned;
- `three-perspective-swot.md` scores 1-5 across five dimensions while the schema
  carries a single 0-10 score per perspective; that contract is unreconciled;
- no end-to-end run against the bound 11.2 checkout has been performed.
