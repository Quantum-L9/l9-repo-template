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
| `pyproject.toml` / `uv.lock` | Python project contract + locked dependency graph | ALREADY_HAVE | repository |
| `requirements.txt` | Dependency source of truth | REJECT_DUPLICATED_AUTHORITY | `pyproject.toml` + `uv.lock` own dependencies; export only when a downstream platform requires it |
| `AGENTS.md` | Cross-agent repository operating law | ALREADY_HAVE | repository |
| `CLAUDE.md` | Thin Claude-specific overlay delegating to `AGENTS.md` + `.l9/*` | ADD_CRITICAL | L9 agent-doc pattern |
| `llms.txt` | Machine-readable discovery map into authoritative repo surfaces | ADD_CRITICAL | L9 repo pattern |
| `bootstrap.sh` | Root setup facade into `tools.l9_repo setup`; no duplicate setup logic | ADD_CRITICAL | repository execution runtime |
| `.gitattributes` | Deterministic text/EOL and binary classification | HARDEN | repository |
| `.pre-commit-config.yaml` | Local mechanical pre-commit enforcement | HARDEN | repository |
| `.semgrep/semgrep-rules.yaml` | High-signal generic Python static-security rules | HARDEN | repository |
| `.gitleaks.toml` | Thin extension of Gitleaks built-in defaults | ADD_SECURITY_CONFIG | central scanner / repo-local policy |
| `.coderabbit.yaml` | L9-aware PR review guidance | ADD_REVIEW_CONFIG | L9 review pattern |
| `docs/examples/coderabbit.yaml` | Duplicate sample after root activation | REMOVE_DUPLICATE | superseded by `.coderabbit.yaml` |
| `.github/workflows/codeql.yml` | Repository-local CI orchestration | REJECT_DUPLICATED_CONTROL | CI targeting/execution belongs to the central control plane |
| `.github/codeql/codeql-config.yml` | Local CodeQL query policy | REJECT_DUPLICATED_CONTROL | shared CodeQL policy is centrally owned |
| Alembic (`alembic.ini` / `alembic/`) | Database migration runtime | CONDITIONAL_CARTRIDGE | add only when a downstream repo declares a database/SQLAlchemy capability |
| `scripts/inventory_check.py` | Layout + mention drift | PORT_SURGICAL | Node-Template verify_contracts idea |
| `scripts/repo_hygiene_audit.py` | eval/exec/print + scaffold bans | PORT_SURGICAL | Node-Template audit_engine (generic) |
| `scripts/reconcile_plugin_config.py` | Chassis metadata describes THIS repo, not the template | ALREADY_HAVE | this repo |
| `scripts/birth-runner/new_repo.py` | One-command birth state machine (9 stages) | ALREADY_HAVE | this repo |
| `scripts/birth-runner/birth_provenance.py` | Birth-record shapes + digests, shared by engine and checker | ALREADY_HAVE | this repo |
| `scripts/birth-runner/verify_birth_integrity.py` | P0 proof that a repo is what its birth record claims | ALREADY_HAVE | this repo |
| `scripts/birth-runner/payload-ownership.yaml` | Authoritative-vs-additive product/chassis ownership | ALREADY_HAVE | this repo |
| `scripts/birth-runner/canonical_ci.py` | Birth state machine + canonical-CI correlation (BIRTH-CI-001..005) | ALREADY_HAVE | this repo |
| `scripts/birth-runner/payload_ownership.py` | One reader for that contract, shared by engine and compiler | ALREADY_HAVE | this repo |
| `scripts/birth-runner/compile_birth_payload.py` | Compiles `l9.birth-payload/v1` from an immutable source snapshot | ALREADY_HAVE | this repo |
| `scripts/birth-runner/verify_birth_payload.py` | Reproduces a compiled payload against its source before assembly | ALREADY_HAVE | this repo |
| `scripts/birth-runner/schemas/birth-payload.schema.json` | Published `l9.birth-payload/v1` contract | ALREADY_HAVE | this repo |
| `scripts/birth-runner/0*.sh` | Staged debugging surfaces | PORT_SURGICAL | PackageTemplate dep-build-runner mechanics |
| `.l9/org-birth-profile.yaml` | Declares the org repo class; carries the immutable `birth:` record in a newborn | ALREADY_HAVE | Quantum-L9/.github contract |
| `src/*/settings|errors|health|retry.py` | Optional package helpers | PORT_SURGICAL | PackageTemplate concepts |
| `.cursor/rules/templates/l9-python-repo.mdc.template` | Generic agent rule | PORT_SURGICAL | Node-Template contract rule rewrite |
| `.cursor/rules/templates/fastapi.mdc.template` | FastAPI conventions — `L9_RENDER_REQUIRES: app_entrypoint` | PORT_SURGICAL | Node-Template fastapi rule |
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

## Baseline hardening ownership

`CLAUDE.md`, `llms.txt`, `bootstrap.sh`, `.gitattributes`, pre-commit,
`.gitleaks.toml`, and `.coderabbit.yaml` are repository chassis surfaces. The
birth payload ownership contract keeps them when an authoritative product
payload replaces the example product tree.

Gitleaks uses the built-in detection corpus with a thin repo-local extension.
Semgrep stays repo-local only for a small high-signal generic rule set that
downstream repositories may extend. Neither surface owns CI scheduling.

No repository-local CodeQL workflow is distributed. Shared CodeQL execution and
query policy remain centrally owned, consistent with `AGENTS.md`'s prohibition
on repository-local CI orchestration.

Alembic and generated `requirements.txt` exports are downstream capability
surfaces, not base-template dependency authorities.

## Inherited organization defaults

GitHub inherits these surfaces from `Quantum-L9/.github` organization defaults
automatically — this repository does not carry copies:

- `CODE_OF_CONDUCT.md` (root)
- `.github/FUNDING.yml`
- `.github/ISSUE_TEMPLATE/*`
- `.github/pull_request_template.md`

Repository-local copies of these names remain a supported explicit override:
a repository that needs different content adds its own file and GitHub prefers it.

`CONTRIBUTING.md`, `SECURITY.md`, and `SUPPORT.md` are kept repository-local.
`.github/CODEOWNERS`, `dependabot.yml`, and `labels.yml` are not inheritable and
stay repo-local.

Which organization capabilities a repository receives is decided by its class
in `Quantum-L9/.github` `policies/repo-classes.yml`, declared here in
`.l9/org-birth-profile.yaml`. The `non_constellation_python` class FORBIDs the
legacy organization-CI distribution set, so the organization seeder cannot
write a file this template then fails closed on.
