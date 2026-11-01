# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.3.0] — 2026-10-09

### Changed

- BIRTH-ARCH-REVISION-001 — compiler-backed birth without Program Execution. `l9.product-birth-binding/v2` supersedes v1: the mandatory `l9.repo-birth-contract/v1` and its IdeaOS / GAR / Plan / campaign / PE lineage are no longer birth prerequisites. The binding now carries the exact semantic-compiler engine and the exact input paths the ProductManifest was compiled from; PREPARE proves the engine checkout against `scripts/birth-runner/semantic-compiler.pin.json` (`Quantum-L9/l9-semantic-compiler-engine`, pinned revision and version), re-runs its `product-build` in an isolated interpreter against the verified payload, and refuses birth on compiler failure, digest or document disagreement, an unresolved entry, an unknown authority, an input the payload does not authorize, or a snapshot the compiler touched (`scripts/birth-runner/product_resolution.py`).
- `package_birth_handoff.py` takes `--semantic-compiler-src` instead of `--evidence` and emits `product-manifest.json` (the engine's output, rendered by the factory) beside the payload and the binding; `--operation` is gone. The adapter's `--birth-contract` argument, the engine's `--repo-birth-contract`, the front door's `--repo-birth-contract-path`, the workflow input `repo_birth_contract_path` and the Make variables `REPO_BIRTH_CONTRACT*` are removed; `--semantic-compiler-src` / `SEMANTIC_COMPILER_SRC` is added. The dispatch workflow fetches the pinned engine with the read-only source token for an adapter-backed birth and proves its SHA before PREPARE.
- The retired v1 schemas are kept as historical evidence under `scripts/birth-runner/schemas/superseded/`; no gate reads them and a v1 binding is refused as a schema-identity failure. Payload compilation, source/tree verification, per-file digests, factory identity, organization authorization, PREPARE/PUBLISH privilege separation, rollback, canonical CI enrolment and remote attestation are unchanged.

## [2.2.0] — 2026-10-02

### Changed

- Identity: `l9-repo-template` is the generic L9 repository birth factory. It owns how a repository is born, not what semantic product is born; ProductTopology/ProductManifest/ProductKind/archetype semantics are upstream inputs (`Quantum-L9/.github` `semantics/`). Retired the non-Constellation museum boundary and the L9-Node-Template / Constellation.PackageTemplate sibling delegation.
- Chassis validation (`inventory_check.py`, `repo_hygiene_audit.py`, generated Cursor rules) is product-kind-neutral: no Node-, engine-, contract-, nodespec-, Gate- or SDK-shaped surface is rejected by shape. Org-CI distribution denial, tools allowlist, and eval/exec/print hygiene are unchanged.
- Birth stage 4 resolves the organization repo class only through `Quantum-L9/.github` `ops/repo-class-profile.js` from the pinned checkout (`resolve_org_profile`); the Python parser/resolver duplicate is removed. Unknown class and malformed policy fail closed in the owner's code.
- The template copy no longer contributes `.github/CODEOWNERS`, `.github/dependabot.yml`, or `.github/labels.yml` to a newborn; MATERIALIZE supplies the organization's current versions, and an explicit payload-supplied copy still wins (missing-only).
- The set of template paths withheld from a newborn is derived per birth from the resolved organization profile through the organization's own `build-seed-payload.js` (`org_materialize_destinations`), not from a static list: for the `default` class that includes `CONTRIBUTING.md` and `SECURITY.md`. Stage 2 and stage 4 share one `OrgAuthority` resolution. `--org-profile-src` must be the clean root of a `Quantum-L9/.github` clone at a 40-hex HEAD (detached is fine); dirty or wrong-repository authority fails closed so `org_policy_sha` names the bytes executed. `docs/ops/SECRET_ROTATION_CHECKLIST.md` no longer routes work to a retired sibling template.
- `CLASS` / `--repo-class` remains `non_constellation_python` by default and means organization birth/distribution profile only — never ProductKind. The birth payload contract `l9.birth-payload/v1` and `repository_shape` (payload authority mode only) are unchanged.

## [Unreleased]

### Changed

- Identity correction: museum is non-Constellation Quantum-L9 Python template (side-by-side with L9-Node-Template and Constellation.PackageTemplate)
- Default example is thin FastAPI hello + optional PackageTemplate-style helpers (no constellation-node-sdk / create_node_app / handlers / spec.yaml)

### Added

- `scripts/repo_hygiene_audit.py` + Semgrep museum hygiene rules
- `scripts/birth-runner/` generic Use-template → rename → verify (`OPEN_PR=0`)
- Parametric Cursor rules `l9-python-repo` + `fastapi` for generic repos
- Docs: WHEN_TO_USE, VALIDATION, LIFECYCLE, ops/REPO_BIRTH
- Tests reorganized under `tests/unit` + `tests/integration`

### Added

- Core thin Makefile facade + `Repo.mk` product targets + `gov-*` WS= wrappers
- Vendored `tools/l9_repo` repository-execution runtime (`L9_REPO_RUNTIME_PIN`)
- In-repo `make pr-check` (`OPEN_PR=0`) and `make agent-check` via Core runtime

- Gate-routed worker shell via constellation-node-sdk (`app.py` / `handlers.py` / `spec.yaml`)
- uv Dockerfile + thin docker-compose; `make run` / `dev` / `wait-http` / `preflight`
- Optional file-inv observability compose (`make obs-up`)
- `.semgrep/semgrep-rules.yaml` wired into l9-analysis
- docs/examples (CodeRabbit, SLO alerts) + secret-rotation checklist
- Parametric Cursor rules renderer (`make render-rules` / `check-rules`) from file-inv DX
- Thin `.vscode` / `.devcontainer` surfaces
- Thin L9 Python GitHub Template skeleton (`l9_example_pkg`)
- `make verify`, `make sync-ci`, and `make rename` force-multipliers
- CI surfaces seeded from `Quantum-L9/.github` via `make sync-ci`
