# Template inventory

Identity: generic **L9 repository birth factory**. This repository owns how an
L9 repository is born; product semantics (ProductTopology, ProductManifest,
ProductKind, archetypes) are upstream inputs owned by `Quantum-L9/.github`
`semantics/` and the product semantic owner.

## Source pins (harvest)

| Source | SHA | Role |
|--------|-----|------|
| Quantum-L9/l9-ci-core | `l9_ci_core_harvest_revision` in `.l9/runtime-provenance.yaml` | `tools/l9_repo` vendored |
| Quantum-L9/.github | recorded per birth in `.l9/org-birth-profile.yaml` (`org_policy_sha`) | repo-class resolver + seed payload builder, invoked at birth, never copied |

Earlier DX harvests from retired sibling templates are history, not law: no
active surface delegates a product kind to them.

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
| `scripts/inventory_check.py` | Chassis layout + discovery wiring + org-CI denial; product-kind-neutral | ALREADY_HAVE | this repo |
| `scripts/repo_hygiene_audit.py` | eval/exec/print ban + single task runner; product-kind-neutral | ALREADY_HAVE | this repo |
| `scripts/reconcile_plugin_config.py` | Chassis metadata describes THIS repo, not the template | ALREADY_HAVE | this repo |
| `scripts/birth-runner/new_repo.py` | Birth state machine (prepare → seal → publish) | ALREADY_HAVE | this repo |
| `scripts/birth-runner/new_repo_legacy.py` | Stage implementations; resolves the org class through `Quantum-L9/.github` `ops/repo-class-profile.js` | ALREADY_HAVE | this repo |
| `scripts/birth-runner/birth_provenance.py` | Birth-record shapes + digests, shared by engine and checker | ALREADY_HAVE | this repo |
| `scripts/birth-runner/verify_birth_integrity.py` | P0 proof that a repo is what its birth record claims | ALREADY_HAVE | this repo |
| `scripts/birth-runner/payload-ownership.yaml` | Authoritative-vs-additive product/chassis ownership (`repository_shape` is payload-authority evidence only) | ALREADY_HAVE | this repo |
| `scripts/birth-runner/canonical_ci.py` | Birth state machine + canonical-CI correlation (BIRTH-CI-001..005) | ALREADY_HAVE | this repo |
| `scripts/birth-runner/payload_ownership.py` | One reader for that contract, shared by engine and compiler | ALREADY_HAVE | this repo |
| `scripts/birth-runner/compile_birth_payload.py` | Compiles `l9.birth-payload/v1` from an immutable source snapshot | ALREADY_HAVE | this repo |
| `scripts/birth-runner/verify_birth_payload.py` | Reproduces a compiled payload against its source before assembly | ALREADY_HAVE | this repo |
| `scripts/birth-runner/schemas/birth-payload.schema.json` | Published `l9.birth-payload/v1` contract | ALREADY_HAVE | this repo |
| `scripts/birth-runner/birth_frontdoor.py` | Remote birth front door (`make birth`) | ALREADY_HAVE | this repo |
| `scripts/birth-runner/l9_birth_adapter.py` | Product-to-birth adapter boundary: binds an already-resolved ProductManifest + realized source + `l9.repo-birth-contract/v1` to factory coordinates; PREPARE refuses assembly unless it admits the bundle | ALREADY_HAVE | this repo |
| `scripts/birth-runner/package_birth_handoff.py` | Packages source + lineage evidence + a supplied ProductManifest into payload, birth contract and product-birth binding; proves the bundle with the adapter | ALREADY_HAVE | this repo |
| `scripts/birth-runner/schemas/birth-contract.schema.json` | Published `l9.repo-birth-contract/v1` contract (moved unchanged from Cursor-Governance `skills/l9-repo-birth`) | ALREADY_HAVE | this repo |
| `scripts/birth-runner/schemas/l9-product-birth-binding.schema.json` | Published `l9.product-birth-binding/v1` contract (closed shape; no repository-shape or kind-hint input) | ALREADY_HAVE | this repo |
| `scripts/birth-runner/0*.sh` | Staged debugging surfaces | ALREADY_HAVE | this repo |
| `.l9/org-birth-profile.yaml` | Declares the org repo class (an organization birth class, not a ProductKind); carries the immutable `birth:` record in a newborn | ALREADY_HAVE | Quantum-L9/.github contract |
| `src/*/settings|errors|health|retry.py` | Reference-payload helpers | REFERENCE_PAYLOAD | this repo |
| `.cursor/rules/templates/l9-python-repo.mdc.template` | Generic chassis agent rule | ALREADY_HAVE | this repo |
| `.cursor/rules/templates/fastapi.mdc.template` | FastAPI conventions for the reference payload — `L9_RENDER_REQUIRES: app_entrypoint` | REFERENCE_PAYLOAD | this repo |
| `observability/` | Opt-in local obs compose | REFERENCE_PAYLOAD | this repo |
| `plugin-config.yaml` + render | Parametric Cursor rules | ALREADY_HAVE | this repo |
| Justfile | — | REJECT | dual runner beside `make` |
| Fix-B OTel Python package | — | REJECT | compose-only obs |
| Factory-owned parallel CI | — | REJECT | organization CI control plane owns CI targeting |
| Adapter orchestration wiring / ProductTopology loader / semantic compilation / lowering / ProductKind inference | — | NOT_HERE | later adapter stages; the pure binding boundary is `l9_birth_adapter.py`, product semantics stay upstream |

## Product-kind neutrality

Node-, Dependency-, engine-, contract-, nodespec-, Gate- and SDK-shaped surfaces
are legitimate products of this factory. No chassis check denies them by shape.
What a born repository *is* comes from its resolved product semantics upstream.

## Deny at repo root

`Justfile`, and every organization-CI distribution path named in
`scripts/inventory_check.py` `DENY_CI_DISTRIBUTION`.

`tools/` allowed only for `tools/l9_repo/` + `tools/check_workflow_integrity.py`.

## Baseline hardening ownership

`CLAUDE.md`, `llms.txt`, `bootstrap.sh`, `.gitattributes`, pre-commit,
`.gitleaks.toml`, and `.coderabbit.yaml` are repository chassis surfaces. The
birth payload ownership contract keeps them when an authoritative product
payload replaces the reference product tree.

Gitleaks uses the built-in detection corpus with a thin repo-local extension.
Semgrep stays repo-local only for a small high-signal generic rule set that
downstream repositories may extend. Neither surface owns CI scheduling.

No repository-local CodeQL workflow is distributed. Shared CodeQL execution and
query policy remain centrally owned, consistent with `AGENTS.md`'s prohibition
on repository-local CI orchestration.

Alembic and generated `requirements.txt` exports are downstream capability
surfaces, not base-template dependency authorities.

## Organization-owned surfaces

GitHub inherits these from `Quantum-L9/.github` organization defaults
automatically — this repository does not carry copies:

- `CODE_OF_CONDUCT.md` (root)
- `.github/FUNDING.yml`
- `.github/ISSUE_TEMPLATE/*`
- `.github/pull_request_template.md`

Repository-local copies of these names remain a supported explicit override:
a repository that needs different content adds its own file and GitHub prefers it.

`CONTRIBUTING.md`, `SECURITY.md`, and `SUPPORT.md` are kept repository-local.

`.github/CODEOWNERS`, `.github/dependabot.yml`, and `.github/labels.yml` are
organization MATERIALIZE destinations for this repository's class, and
`CONTRIBUTING.md` / `SECURITY.md` are MATERIALIZE destinations for the `default`
class. This repository keeps its own copies for itself, but the template copy
contributes **none** of the destinations the class being born materializes
(`org_materialize_destinations`, asked of the organization's own seed builder
per birth): stage 4 writes the organization's current files from the pinned
`Quantum-L9/.github` checkout, and an explicit product-payload copy still wins
because MATERIALIZE is missing-only.

Which organization capabilities a repository receives is decided by its class
in `Quantum-L9/.github` `policies/repo-classes.yml`, declared here in
`.l9/org-birth-profile.yaml` and resolved at birth by the organization's own
`ops/repo-class-profile.js`. The `non_constellation_python` class FORBIDs the
legacy organization-CI distribution set, so the organization seeder cannot
write a file this template then fails closed on.
