# Template inventory

Identity: **non-Constellation** Quantum-L9 Python museum. Sibling templates own nodes and deps.

## Source pins (harvest)

| Source | SHA | Role |
|--------|-----|------|
| Quantum-L9/L9-Node-Template | `8999fd1` (tree at mine) | DX gold only — REJECT_WRONG_PRODUCT for node/codegen surfaces |
| Quantum-L9/Constellation.PackageTemplate | `dcb5d24` (tree at mine) | DX gold only — REJECT_WRONG_PRODUCT for constellation_* birth plays |
| Quantum-L9/l9-ci-core | `l9_ci_core_harvest_revision` in `.l9/runtime-provenance.yaml` | `tools/l9_repo` vendored |

## Surfaces

| Path | Role | Classification | Source |
|------|------|----------------|--------|
| `Makefile` / `Repo.mk` / `tools/l9_repo/` | Core facade + product/gov wrappers | ALREADY_HAVE | l9-ci-core |
| `scripts/inventory_check.py` | Layout + mention drift | PORT_SURGICAL | Node-Template verify_contracts idea |
| `scripts/repo_hygiene_audit.py` | eval/exec/print + scaffold bans | PORT_SURGICAL | Node-Template audit_engine (generic) |
| `scripts/birth-runner/new_repo.py` | One-command birth state machine (8 stages) | ALREADY_HAVE | this repo |
| `scripts/birth-runner/0*.sh` | Staged debugging surfaces | PORT_SURGICAL | PackageTemplate dep-build-runner mechanics |
| `.l9/org-birth-profile.yaml` | Declares the org repo class | ALREADY_HAVE | Quantum-L9/.github contract |
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
| Museum-owned parallel CI | — | REJECT | organization CI control plane owns CI targeting |

## Deny at repo root

`engine/`, `chassis/`, `domains/`, `client/`, `database/`, `deploy/`, `example_service/`, `contracts/`, `Justfile`

`tools/` allowed only for `tools/l9_repo/` + `tools/check_workflow_integrity.py`.

## Inherited organization defaults

GitHub inherits these surfaces from `Quantum-L9/.github` organization
defaults automatically — this repository does not carry copies:

- `CODE_OF_CONDUCT.md` (root)
- `.github/FUNDING.yml`
- `.github/ISSUE_TEMPLATE/*` (9 issue forms)
- `.github/pull_request_template.md`

Repository-local copies of these names remain a supported explicit override:
a repo that needs different content adds its own file and GitHub prefers it.

`CONTRIBUTING.md`, `SECURITY.md`, and `SUPPORT.md` are kept repository-local
because this template customizes them for the museum. `.github/CODEOWNERS`,
`dependabot.yml`, and `labels.yml` are not inheritable and stay repo-local.
CI targeting and governance invocation belong to the future organization CI
control plane (l9-ci-core / l9-ci-control-plane).

Which of these a repository actually receives is decided by its class in
`Quantum-L9/.github` `policies/repo-classes.yml`, declared here in
`.l9/org-birth-profile.yaml`. The `non_constellation_python` class FORBIDs the
whole `DENY_CI_DISTRIBUTION` set, so the organization seeder can never write a
file this template then fails closed on.
