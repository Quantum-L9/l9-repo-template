# Architecture — l9-repo-template

Generic Quantum-L9 **repository birth factory**.

## Role split

| Concern | Owner |
|---------|-------|
| How an L9 repository is born | **this repo** — `make new-repo` / `make birth` |
| What semantic product is born (ProductTopology, ProductManifest, ProductKind, archetypes) | `Quantum-L9/.github` `semantics/` + the product semantic owner (upstream input) |
| What the organization requires of a born repository | `Quantum-L9/.github` — `policies/repo-classes.yml`, `ops/repo-class-profile.js` |
| Birthing adapter + packaging (resolved semantics → admissible birth bundle) | **this repo** — `scripts/birth-runner/l9_birth_adapter.py`, `package_birth_handoff.py`; consumes ProductManifest, never produces it |

Repository birth profile, repository shape, payload mode, SDK presence and Gate
presence are **not** ProductKind. The factory never infers product kind from any
of them.

## Layout

```
Makefile                 # Core-generated make-v1 facade (Repository Execution V2)
Repo.mk                  # repo-setup/validate/check/test leaves + product targets + gov-* WS= wrappers
scripts/birth-runner/    # new_repo.py birth engine + payload compiler/verifier + provenance
src/<pkg>/               # Reference example payload (thin FastAPI hello + helpers)
tests/unit|integration/  # package + chassis compliance tests
observability/           # optional local Grafana/Prom/Tempo/OTelCol (reference payload)
.github/                 # repository-local GitHub config only
.l9/repo-workflow.json       # l9.repo-execution/v2 contract (three fields)
.l9/org-birth-profile.yaml   # the org repo class this repository declares
```

## Ownership split

| Surface | Authority |
|---------|-----------|
| Birth engine, payload contract, provenance | **this repo** — `scripts/birth-runner/` |
| Reference payload boundary (chassis vs product) | `scripts/birth-runner/payload-ownership.yaml` |
| Product Make targets | `Repo.mk` |
| Repository-execution facade | l9-ci-core `make-v1` (generated `Makefile`; `docs/repository-execution-runtime.md`) |
| Governance pr-check / wiring | Cursor-Governance via `gov-*` / `WS=` |
| CI execution semantics | l9-ci-core (future) |
| Organization CI control | l9-ci-control-plane (future) |
| Product semantics / SDK compatibility of a born product | upstream / product-owned |
| What the organization requires | Quantum-L9/.github — `policies/repo-classes.yml` |

## Force multipliers

`make new-repo` · `make birth` · `make rename` · `make verify` · `make pr-check` ·
`make render-rules` · `make run` · `make obs-up` · `make gov-pr-check` ·
`make agent-check` · `make hygiene-check`
