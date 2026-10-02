# Architecture — l9-repo-template

Generic Quantum-L9 **repository birth factory**.

## Role split

| Concern | Owner |
|---------|-------|
| How an L9 repository is born | **this repo** — `make new-repo` / `make birth` |
| What semantic product is born (ProductTopology, ProductManifest, ProductKind, archetypes) | `Quantum-L9/.github` `semantics/` + the product semantic owner (upstream input) |
| What the organization requires of a born repository | `Quantum-L9/.github` — `policies/repo-classes.yml`, `ops/repo-class-profile.js` |
| Birthing adapter (resolved semantics → birth request) | not implemented; boundary only named in `.l9/architecture.yaml` |

Repository birth profile, repository shape, payload mode, SDK presence and Gate
presence are **not** ProductKind. The factory never infers product kind from any
of them.

## Layout

```
Makefile                 # Core thin facade (identical to Makefile.template)
Repo.mk                  # Product targets + gov-* WS= wrappers
tools/l9_repo/           # Vendored repository-execution runtime (Core pin)
scripts/birth-runner/    # new_repo.py birth engine + payload compiler/verifier + provenance
src/<pkg>/               # Reference example payload (thin FastAPI hello + helpers)
tests/unit|integration/  # package + chassis compliance tests
observability/           # optional local Grafana/Prom/Tempo/OTelCol (reference payload)
.github/                 # repository-local GitHub config only
.l9/runtime-provenance.yaml  # vendored execution-runtime harvest provenance
.l9/org-birth-profile.yaml   # the org repo class this repository declares
```

## Ownership split

| Surface | Authority |
|---------|-----------|
| Birth engine, payload contract, provenance | **this repo** — `scripts/birth-runner/` |
| Reference payload boundary (chassis vs product) | `scripts/birth-runner/payload-ownership.yaml` |
| Product Make targets | `Repo.mk` |
| Repository-execution facade | vendored `tools/l9_repo` |
| Governance pr-check / wiring | Cursor-Governance via `gov-*` / `WS=` |
| CI execution semantics | l9-ci-core (future) |
| Organization CI control | l9-ci-control-plane (future) |
| Product semantics / SDK compatibility of a born product | upstream / product-owned |
| What the organization requires | Quantum-L9/.github — `policies/repo-classes.yml` |

## Force multipliers

`make new-repo` · `make birth` · `make rename` · `make verify` · `make pr-check` ·
`make render-rules` · `make run` · `make obs-up` · `make gov-pr-check` ·
`make agent-check` · `make hygiene-check`
