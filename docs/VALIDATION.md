# Validation honesty

What green means for this museum template.

| Gate | Command | Proves |
|------|---------|--------|
| Inventory | `make inventory-check` | Required files, deny dirs, no Gate-worker defaults, tools allowlist |
| Hygiene | `make hygiene-check` | No eval/exec/print in `src/`; no Justfile/contracts/enginehandlers reintro |
| Cursor rules | `make check-rules` | Rendered `.mdc` matches templates + `plugin-config.yaml` |
| Lint / types | `make lint` / `make typecheck` | Ruff + mypy |
| Tests | `make test` | Unit + integration |
| Product | `make verify` / `make pr-check` | Full local ladder (`OPEN_PR=0`) |
| Core facade | `make agent-check` | Vendored `tools.l9_repo` completion proof |
| Governance | `make gov-pr-check` | Cursor-Governance against `WS=$(pwd)` when wired |

## What green does **not** prove

- Constellation transport / Gate routing correctness (belongs to L9-Node-Template / Gate_SDK)
- `constellation_*` dependency birth (belongs to PackageTemplate)
- Production observability (optional `make obs-up` is local compose only)
- That this repo should be used for nodes or dep packages — see [WHEN_TO_USE.md](WHEN_TO_USE.md)
