# Architecture — l9-repo-template

Gate-routed worker head-start for Quantum-L9.

## Layout

```
src/<pkg>/app.py       # create_node_app wiring
src/<pkg>/handlers.py  # @register_handler domain drop-in
spec.yaml              # Gate registration spec
tests/                 # smoke + worker + rename/render tests
scripts/               # verify / sync-ci / rename / render / wait / preflight
observability/         # optional local Grafana/Prom/Tempo/OTelCol (make obs-up)
.semgrep/              # local Semgrep policy wired into l9-analysis
.github/               # org pack via make sync-ci
.l9/ci-pin             # org + Core + Gate_SDK pins
```

## Boundaries

| Surface | Authority |
|---------|-----------|
| TransportPacket / Gate egress | constellation-node-sdk (Gate_SDK pin) |
| CI pack / governance | Quantum-L9/.github via sync-ci |
| Local obs compose | file-inv pack (opt-in) |
| Domain handlers | derived repo |

## Force multipliers

`make rename` · `make verify` · `make sync-ci` · `make render-rules` · `make run` · `make obs-up`
