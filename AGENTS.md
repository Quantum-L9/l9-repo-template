# AGENTS.md — Quantum-L9 repository birth factory

## Mission

Generic L9 repository birth factory. This repository owns **how** an L9
repository is born. It does not own **what** semantic product is being born.

## Authority contracts

- [`.l9/architecture.yaml`](.l9/architecture.yaml)
- [`.l9/ownership.yaml`](.l9/ownership.yaml)
- [`.l9/sdk-compatibility.yaml`](.l9/sdk-compatibility.yaml)

## Owns

- Birth engine under `scripts/birth-runner/`: assembly, compiled payload
  production/verification, provenance, lifecycle, publication, attestation
- Local verify + Cursor rule drift + optional local obs stack
- Product Make targets in `Repo.mk`
- Reference example payload under `src/` (thin FastAPI hello + optional helpers)

## Upstream inputs (not owned here)

- Product semantics — ProductTopology, ProductManifest, ProductKind, node and
  dependency archetypes — are owned by `Quantum-L9/.github` `semantics/` and the
  product semantic owner. They arrive as resolved inputs.
- The Python/FastAPI content is a reference payload, not factory law.
- SDK compatibility of a born product is product-owned.
- The repository's own org birth class is `non_constellation_python` — an
  organization birth/distribution class, not a ProductKind.

## Never

- Infer ProductKind from repository shape, package contents, SDK presence, Gate
  presence, repo class, or template ancestry
- Implement or simulate the birthing adapter, a ProductTopology/ProductManifest
  loader, or a semantic compiler here
- Maintain an independent copy of organization repo-class semantics
- Adding repository-local CI orchestration — CI execution semantics belong to l9-ci-core
- Hand-editing generated `.cursor/rules/*.mdc`
- Copying Cursor-Governance Makefile/ops into this repo
- Requiring `make obs-up` for verify/CI
- Editing root `Makefile` by hand — must match `tools/l9_repo/Makefile.template`

## When to use

See [docs/WHEN_TO_USE.md](docs/WHEN_TO_USE.md).

## Agent completion contract

1. Product green: `make verify` (or `make pr-check`)
2. When Cursor-Governance is wired: `make gov-pr-check`
3. Prefer `make gov-pr` to open/remediate PRs — in-repo `OPEN_PR` stays `0`
4. Optional Core facade proof: `make agent-check`

## Validation ladder

```bash
make inventory-check
make hygiene-check
make check-config
make check-rules
make lint
make typecheck
make test
# or: make verify
```

## Governance control plane (WS=)

```bash
make gov-pr-check
make -C "$HOME/.cursor-governance" pr-check WS="$(pwd)"
```

## CI ownership boundary

- Repository owns deterministic local verification: `make verify` / `make ci`
  (inventory, hygiene, rules, lint, typecheck, pytest) via `.l9/repo-workflow.json`.
- l9-ci-core owns CI execution semantics (future invocation through the
  repository execution contract).
- l9-ci-control-plane owns organization CI targeting, versioning, and
  enforcement (future).
- This repository must not distribute, copy, pin, or synchronize organization
  CI implementation.
