# Template inventory

Identity: **non-Constellation** Quantum-L9 Python museum. Sibling templates own nodes and deps.

## Source pins (harvest)

| Source | SHA | Role |
|--------|-----|------|
| Quantum-L9/L9-Node-Template | `8999fd1` (tree at mine) | DX gold only — REJECT_WRONG_PRODUCT for node/codegen surfaces |
| Quantum-L9/Constellation.PackageTemplate | `dcb5d24` (tree at mine) | DX gold only — REJECT_WRONG_PRODUCT for constellation_* birth plays |
| Quantum-L9/l9-ci-core | `L9_REPO_RUNTIME_PIN` in `.l9/ci-pin` | `tools/l9_repo` vendored |
| Quantum-L9/.github | `ORG_GITHUB_SHA` | CI via sync-ci |

## Surfaces

| Path | Role | Classification | Source |
|------|------|----------------|--------|
| `Makefile` / `Repo.mk` / `tools/l9_repo/` | Core facade + product/gov wrappers | ALREADY_HAVE | l9-ci-core |
| `scripts/inventory_check.py` | Layout + mention drift | PORT_SURGICAL | Node-Template verify_contracts idea |
| `scripts/repo_hygiene_audit.py` | eval/exec/print + scaffold bans | PORT_SURGICAL | Node-Template audit_engine (generic) |
| `scripts/birth-runner/` | Use-template → rename → verify | PORT_SURGICAL | PackageTemplate dep-build-runner mechanics |
| `src/*/settings|errors|health|retry.py` | Optional package helpers | PORT_SURGICAL | PackageTemplate concepts |
| `.cursor/rules/templates/l9-python-repo.mdc.template` | Generic agent rule | PORT_SURGICAL | Node-Template contract rule rewrite |
| `.cursor/rules/templates/fastapi.mdc.template` | FastAPI conventions | PORT_SURGICAL | Node-Template fastapi rule |
| `observability/` | Opt-in local obs compose | ALREADY_HAVE | file-inv |
| `plugin-config.yaml` + render | Parametric Cursor rules | ALREADY_HAVE | file-inv DX |
| `create_node_app` / Gate handlers / `spec.yaml` Gate registration | — | REJECT_WRONG_PRODUCT | belongs in L9-Node-Template |
| `enginehandlers` / `nodespec` / `contracts/` | — | REJECT_WRONG_PRODUCT | Node-Template legacy |
| PacketEnvelope / Gate peer-HTTP museum gates | — | REJECT_WRONG_PRODUCT | node/SDK law |
| Justfile | — | REJECT | dual runner |
| Fix-B OTel Python package | — | REJECT | compose-only obs |
| PackageTemplate plays / PyPI release | — | REJECT_WRONG_PRODUCT | dep factory |
| Museum-owned parallel CI | — | REJECT | sync-ci only |

## Deny at repo root

`engine/`, `chassis/`, `domains/`, `client/`, `database/`, `deploy/`, `example_service/`, `contracts/`, `Justfile`

`tools/` allowed only for `tools/l9_repo/` + `tools/check_workflow_integrity.py`.
