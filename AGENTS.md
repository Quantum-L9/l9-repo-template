# AGENTS.md — Quantum-L9 non-Constellation Python template

## Mission

Generic Quantum-L9 Python GitHub Template for runtimes, side projects, and experiments
**outside** Constellation. Not a node scaffold. Not a `constellation_*` dep scaffold.

## Authority contracts

- [`.l9/architecture.yaml`](.l9/architecture.yaml)
- [`.l9/ownership.yaml`](.l9/ownership.yaml)
- [`.l9/sdk-compatibility.yaml`](.l9/sdk-compatibility.yaml)

## Owns

- Example package under `src/` (thin FastAPI hello + optional helpers)
- Local verify + Cursor rule drift + optional local obs stack
- Product Make targets in `Repo.mk`
- Generic birth runner under `scripts/birth-runner/`

## Never

- Become a Constellation node template (`create_node_app`, Gate handlers, TransportPacket routing)
- Become a `constellation_*` dependency birth factory
- `engine/`, `chassis/`, `domains/`, Poetry, Sonar, Justfile, golden parallel CI
- Adding repository-local CI orchestration — CI execution semantics belong to l9-ci-core
- Hand-editing generated `.cursor/rules/*.mdc`
- Copying Cursor-Governance Makefile/ops into this repo
- Requiring `make obs-up` for verify/CI
- Editing root `Makefile` by hand — must match `tools/l9_repo/Makefile.template`

## Sibling templates

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
