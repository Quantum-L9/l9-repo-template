# Template inventory

Identity: **non-Constellation** Quantum-L9 Python museum. Sibling templates own nodes and deps.

## Source pins (harvest)

| Source | SHA | Role |
|--------|-----|------|
| Quantum-L9/L9-Node-Template | `8999fd1` (tree at mine) | DX gold only - REJECT_WRONG_PRODUCT for node/codegen surfaces |
| Quantum-L9/Constellation.PackageTemplate | `dcb5d24` (tree at mine) | DX gold only - REJECT_WRONG_PRODUCT for constellation_* birth plays |
| Quantum-L9/l9-ci-core | `l9_ci_core_harvest_revision` in `.l9/runtime-provenance.yaml` | `tools/l9_repo` vendored |

## Surfaces

| Path | Role | Classification | Source |
|------|------|----------------|--------|
| `Makefile` / `Repo.mk` / `tools/l9_repo/` | Core facade + product/gov wrappers | ALREADY_HAVE | l9-ci-core |
| `pyproject.toml` / `uv.lock` | Python project contract + locked dependency graph | ALREADY_HAVE | repository |
| `requirements.txt` | Dependency source of truth | REJECT_DUPLICATED_AUTHORITY | `pyproject.toml` + `uv.lock` own dependencies; export only when a downstream platform requires it |
| `AGENTS.md` | Cross-agent repository operating law | ALREADY_HAVE | repository |
| `CLAUDE.md` | Thin Claude-specific overlay that delegates to `AGENTS.md` + `.l9/*` | ADD_CRITICAL | L9 agent-doc pattern |
| `llms.txt` | Machine-readable discovery map into authoritative repo surfaces | ADD_CRITICAL | L9 repo pattern |
| `bootstrap.sh` | Root setup facade into `tools.l9_repo setup`; no duplicate setup logic | ADD_CRITICAL | repository execution runtime |
| `.gitattributes` | Deterministic text/EOL and binary classification | ALREADY_HAVE_HARDEN | repository |
| `.pre-commit-config.yaml` | Local mechanical pre-commit enforcement | ALREADY_HAVE_REQUIRED | repository |
| `.semgrep/semgrep-rules.yaml` | High-signal generic Python static-security rules | ALREADY_HAVE_HARDEN | repository |
| `.gitleaks.toml` | Thin extension of Gitleaks built-in defaults, consumed by L9 security CI | ADD_SECURITY_CONFIG | l9-ci-core security contract |
| `.coderabbit.yaml` | L9-aware PR review guidance | ADD_REVIEW_CONFIG | L9 review pattern |
| `docs/examples/coderabbit.yaml` | Duplicate opt-in CodeRabbit sample after root activation | REMOVE_DUPLICATE | superseded by `.coderabbit.yaml` |
| `.github/workflows/codeql.yml` | Thin caller to centrally owned CodeQL reusable workflow | ADD_SECURITY_CALLER | Cursor-Governance canonical caller |
| `.github/codeql/codeql-config.yml` | Local CodeQL query policy | REJECT_DUPLICATED_CONTROL | centralized in Cursor-Governance |
| Alembic (`alembic.ini` / `alembic/`) | Database migration runtime | CONDITIONAL_CARTRIDGE | add only when a downstream repo declares a database/SQLAlchemy capability |
| `scripts/inventory_check.py` | Layout + mention drift | PORT_SURGICAL | Node-Template verify_contracts idea |
| `scripts/repo_hygiene_audit.py` | eval/exec/print + scaffold bans | PORT_SURGICAL | Node-Template audit_engine (generic) |
| `scripts/birth-runner/` | Use-template -> rename -> verify | PORT_SURGICAL | PackageTemplate dep-build-runner mechanics |
| `src/*/settings|errors|health|retry.py` | Optional package helpers | PORT_SURGICAL | PackageTemplate concepts |
| `.cursor/rules/templates/l9-python-repo.mdc.template` | Generic agent rule | PORT_SURGICAL | Node-Template contract rule rewrite |
| `.cursor/rules/templates/fastapi.mdc.template` | FastAPI conventions | PORT_SURGICAL | Node-Template fastapi rule |
| `observability/` | Opt-in local obs compose | ALREADY_HAVE | file-inv |
| `plugin-config.yaml` + render | Parametric Cursor rules | ALREADY_HAVE | file-inv DX |
| `create_node_app` / Gate handlers / `spec.yaml` Gate registration | - | REJECT_WRONG_PRODUCT | belongs in L9-Node-Template |
| `enginehandlers` / `nodespec` / `contracts/` | - | REJECT_WRONG_PRODUCT | Node-Template legacy |
| PacketEnvelope / Gate peer-HTTP museum gates | - | REJECT_WRONG_PRODUCT | node/SDK law |
| Justfile | - | REJECT | dual runner |
| Fix-B OTel Python package | - | REJECT | compose-only obs |
| PackageTemplate plays / PyPI release | - | REJECT_WRONG_PRODUCT | dep factory |
| Museum-owned parallel CI | - | REJECT | organization CI control plane owns CI targeting |

## Deny at repo root

`engine/`, `chassis/`, `domains/`, `client/`, `database/`, `deploy/`, `example_service/`, `contracts/`, `Justfile`

`tools/` allowed only for `tools/l9_repo/` + `tools/check_workflow_integrity.py`.

## Inherited organization defaults

GitHub inherits these surfaces from `Quantum-L9/.github` organization
defaults automatically - this repository does not carry copies:

- `CODE_OF_CONDUCT.md` (root)
- `.github/FUNDING.yml`
- `.github/ISSUE_TEMPLATE/*` (9 issue forms)
- `.github/pull_request_template.md`

Repository-local copies of these names remain a supported explicit override:
a repo that needs different content adds its own file and GitHub prefers it.

`CONTRIBUTING.md`, `SECURITY.md`, and `SUPPORT.md` are kept repository-local
because this template customizes them for the museum. `.github/CODEOWNERS`,
`dependabot.yml`, and `labels.yml` are not inheritable and stay repo-local.

CodeQL is a deliberate thin-caller exception, not duplicated CI ownership.
This template carries `.github/workflows/codeql.yml`, while the reusable
execution and shared query policy remain centralized in
`Quantum-L9/Cursor-Governance`. A repository-local
`.github/codeql/codeql-config.yml` is forbidden because it would fork the
organization source of truth.

Gitleaks follows the same ownership principle. The repo-local `.gitleaks.toml`
extends Gitleaks built-in defaults without copying the default rule corpus;
`l9-ci-core` owns scanner installation and invocation. Semgrep stays repo-local
only for a small high-signal generic rule set that downstream repos may extend.

Alembic and generated `requirements.txt` exports are downstream capability
surfaces, not base-template dependency authorities.

All other CI execution semantics stay in l9-ci-core and organization CI control
stays outside this repository.
