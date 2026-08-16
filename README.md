# l9-repo-template

Thin **Quantum-L9 Python** GitHub Template for repos that live **outside** Constellation
(runtimes, side projects, experiments, misc services).

This template is **not** for Constellation nodes or `constellation_*` dependency packages.
Those already have sibling templates — [L9-Node-Template](https://github.com/Quantum-L9/L9-Node-Template) for nodes, [Constellation.PackageTemplate](https://github.com/Quantum-L9/Constellation.PackageTemplate) for deps — see [docs/WHEN_TO_USE.md](docs/WHEN_TO_USE.md).

## Quick start

1. **Use this template** on GitHub.
2. Rename:

   ```bash
   make rename PKG=your_pkg
   ```

3. Implement package logic under `src/your_pkg/`.
4. Copy `.env.example` → `.env` as needed.
5. Validate and run:

   ```bash
   make verify
   make run
   # optional local Grafana/Prom/Tempo/OTelCol:
   make obs-up
   ```

## Make surfaces (dual ladder)

| Ladder | Command | Role |
|--------|---------|------|
| Product | `make verify` / `make pr-check` | In-repo museum gate (`OPEN_PR=0`) |
| Core facade | `make agent-check` / `make validate` | Vendored `tools.l9_repo` completion proof |
| Governance | `make gov-pr-check` | Cursor-Governance via `WS=$(pwd)` |

```bash
make gov-pr-check
# equivalent:
make -C "$HOME/.cursor-governance" pr-check WS="$(pwd)"
```

## Architecture

- Default example: minimal FastAPI hello (non-Gate)
- Makefile: Core thin facade + `Repo.mk` product targets + `gov-*` wrappers
- CI: org control plane (l9-ci-core execution, l9-ci-control-plane targeting) — no repo-side sync
- Obs stack: optional (`make obs-up`) — not required for `make verify`

See [ARCHITECTURE.md](ARCHITECTURE.md), [TEMPLATE_INVENTORY.md](TEMPLATE_INVENTORY.md),
and [docs/WHEN_TO_USE.md](docs/WHEN_TO_USE.md).
