# Architecture — l9-repo-template

Quantum-L9 Python GitHub Template for **non-Constellation** repos.

## Three-template matrix

| Template | Product role |
|----------|--------------|
| L9-Node-Template | Constellation nodes |
| Constellation.PackageTemplate | `constellation_*` birth dependencies |
| **l9-repo-template** | Runtimes / side projects / experiments outside Constellation |

## Layout

```
Makefile                 # Core thin facade (identical to Makefile.template)
Repo.mk                  # Product targets + gov-* WS= wrappers
tools/l9_repo/           # Vendored repository-execution runtime (Core pin)
scripts/birth-runner/    # new_repo.py one-command birth + staged debug surfaces
src/<pkg>/               # Thin FastAPI hello + optional helpers
tests/unit|integration/  # package + template compliance tests
observability/           # optional local Grafana/Prom/Tempo/OTelCol
.github/                 # repository-local GitHub config only
.l9/runtime-provenance.yaml  # vendored execution-runtime harvest provenance
.l9/org-birth-profile.yaml   # the org repo class this repository declares
```

## Ownership split

| Surface | Authority |
|---------|-----------|
| Constellation nodes | L9-Node-Template (sibling) |
| constellation_* deps | PackageTemplate (sibling) |
| Product Make targets | `Repo.mk` |
| Repository-execution facade | vendored `tools/l9_repo` |
| Governance pr-check / wiring | Cursor-Governance via `gov-*` / `WS=` |
| CI execution semantics | l9-ci-core (future) |
| Organization CI control | l9-ci-control-plane (future) |
| How a repository is born | **this repo** — `make new-repo` |
| What the organization requires | Quantum-L9/.github — `policies/repo-classes.yml` |

## Force multipliers

`make new-repo` · `make rename` · `make verify` · `make pr-check` ·
`make render-rules` · `make run` · `make obs-up` · `make gov-pr-check` ·
`make agent-check` · `make hygiene-check`
