# Architecture — l9-repo-template

Gate-routed worker head-start for Quantum-L9.

## Layout

```
Makefile                 # Core thin facade (identical to Makefile.template)
Repo.mk                  # Product targets + gov-* WS= wrappers
tools/l9_repo/           # Vendored repository-execution runtime (Core pin)
.l9/repo-workflow.json   # setup/check/test matrices for make agent-check
src/<pkg>/app.py         # create_node_app wiring
src/<pkg>/handlers.py    # @register_handler domain drop-in
spec.yaml                # Gate registration spec
tests/                   # smoke + worker + rename/render + makefile tests
scripts/                 # verify / sync-ci / rename / render / wait / preflight
observability/           # optional local Grafana/Prom/Tempo/OTelCol (make obs-up)
.semgrep/                # local Semgrep policy wired into l9-analysis
.github/                 # org pack via make sync-ci
.l9/ci-pin               # org + Core workflow + Gate_SDK + runtime pins
```

## Ownership split (never dual SSOT)

| Surface | Authority |
|---------|-----------|
| TransportPacket / Gate egress | constellation-node-sdk (Gate_SDK pin) |
| CI pack | Quantum-L9/.github via sync-ci |
| Product Make targets | `Repo.mk` |
| Repository-execution facade | vendored `tools/l9_repo` (Core) |
| Governance pr-check / wiring / secrets | Cursor-Governance via `gov-*` / `WS=` |
| Local obs compose | file-inv pack (opt-in) |
| Domain handlers | derived repo |

## Force multipliers

`make rename` · `make verify` · `make pr-check` · `make sync-ci` ·
`make render-rules` · `make run` · `make obs-up` · `make gov-pr-check` ·
`make agent-check`
