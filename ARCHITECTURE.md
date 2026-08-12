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
scripts/birth-runner/    # Generic Use-template → rename → verify
src/<pkg>/               # Thin FastAPI hello + optional helpers
tests/unit|integration/  # package + template compliance tests
observability/           # optional local Grafana/Prom/Tempo/OTelCol
.github/                 # org pack via make sync-ci
.l9/ci-pin               # org + Core workflow + runtime pins
```

## Ownership split

| Surface | Authority |
|---------|-----------|
| Constellation nodes | L9-Node-Template (sibling) |
| constellation_* deps | PackageTemplate (sibling) |
| Product Make targets | `Repo.mk` |
| Repository-execution facade | vendored `tools/l9_repo` |
| Governance pr-check / wiring | Cursor-Governance via `gov-*` / `WS=` |
| CI pack | Quantum-L9/.github via sync-ci |

## Force multipliers

`make rename` · `make verify` · `make pr-check` · `make sync-ci` ·
`make render-rules` · `make run` · `make obs-up` · `make gov-pr-check` ·
`make agent-check` · `make hygiene-check`
