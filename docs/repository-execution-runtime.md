# Repository Execution (V2)

This repository declares Core's **Repository Execution V2** contract
(`l9.repo-execution/v2`). Core's `run-repository-verification` action (pinned in
`Quantum-L9/l9-ci-core` `.github/workflows/org-ci.yml`) validates it and runs
`make setup → validate → check → test` for the required check
`Analyze (central Core)`. This repository is listed in Core's
`contract-policy.json` `required_repositories`, so only a V2 contract is
admitted (`docs/ACTIVATION.md` in l9-ci-core is the consumer contract).

Three files, nothing else:

| File | Owner | Rule |
|---|---|---|
| `.l9/repo-workflow.json` | contract | exactly `schema`, `facade: make-v1`, `required_phases: [setup, validate, check, test]` |
| `Makefile` | Core | the released `make-v1` facade, byte for byte; generated, never hand-edited |
| `Repo.mk` | this repository | the four `.PHONY` leaves `repo-setup`, `repo-validate`, `repo-check`, `repo-test`; must not redefine `help`, `setup`, `validate`, `check`, or `test` |

Regenerate and validate the facade from any Core checkout:

```bash
CONSUMER="$(pwd)"
git clone --depth=1 https://github.com/Quantum-L9/l9-ci-core.git /tmp/l9-ci-core
cd /tmp/l9-ci-core
python3 -m tools.l9_repo --workspace "$CONSUMER" reconcile   # writes $CONSUMER/Makefile
python3 -m tools.l9_repo --workspace "$CONSUMER" validate    # contract + facade + Repo.mk ABI
```

## Phase mapping

| Phase | `Repo.mk` leaf | Runs |
|---|---|---|
| `setup` | `repo-setup` | creates `.venv` and installs the project with `[dev]` extras (`uv sync --locked --extra dev` when `uv` is present, else `venv` + `pip install -e ".[dev]"`) |
| `validate` | `repo-validate` | `inventory-check`, `hygiene-check` |
| `check` | `repo-check` | `ruff check .`, `ruff format --check .`, `mypy src` |
| `test` | `repo-test` | `pytest -q` |

`make agent-check` runs `validate check test` and fails if `HEAD` or the
worktree changed during the run. `make verify` remains the fuller local ladder
(adds `birth-check`, `check-config`, `check-rules`).

## Retired V1 runtime

The template formerly vendored Core's V1 runtime (`schema_version: 1`,
artifact 4.3.1). V2 runtime code is Core-owned and never vendored, so the
following were removed from the template and are refused by
`scripts/inventory_check.py` if they reappear: `tools/l9_repo/**`,
`tools/check_workflow_integrity.py`, `.l9/repo-workflow.schema.json`,
`.l9/runtime-provenance.yaml`, `MANIFEST.sha256`,
`requirements-repo-runtime.txt`, `scripts/regenerate_runtime_manifest.py`.
The V1-only facade verbs (`doctor`, `change-policy`, `status`, `reconcile`,
`push`, `pr`) went with it; publication is Cursor-Governance's `make pr`
(`make gov-pr`).

## Offspring

An ordinary birth copies this contract: the newborn receives the same
three-field `.l9/repo-workflow.json`, the same generated `Makefile`, and this
`Repo.mk`. A repository-shaped payload that supplies its own
`.l9/repo-workflow.json` keeps its own execution surfaces byte for byte, and
this document (`execution_runtime.bound` in
`scripts/birth-runner/payload-ownership.yaml`) is retired from that newborn.
