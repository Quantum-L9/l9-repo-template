# l9-repo-template

Thin **Python Gate-worker** GitHub Template for Quantum-L9.

Use this instead of `cryptoxdog/golden-repo` or the FastAPI/OTel body in
`cryptoxdog/constellation-file-inventory`.

## Quick start

1. **Use this template** on GitHub.
2. Rename:

   ```bash
   make rename PKG=your_pkg
   ```

3. Implement domain logic in `src/your_pkg/handlers.py` (`@register_handler`).
4. Set `.env` from `.env.example` (`GATE_URL`, `L9_ALLOWED_ACTIONS`, …).
5. Validate and run:

   ```bash
   make verify
   make run
   # optional local Grafana/Prom/Tempo/OTelCol:
   make obs-up
   ```

6. Refresh CI after pin bumps: `make sync-ci`

## Make surfaces (dual ladder)

| Ladder | Command | Role |
|--------|---------|------|
| Product | `make verify` / `make pr-check` | In-repo museum gate (`OPEN_PR=0`) |
| Core facade | `make agent-check` / `make validate` | Vendored `tools.l9_repo` completion proof |
| Governance | `make gov-pr-check` | Cursor-Governance via `WS=$(pwd)` |

Governance is **not** copied into this repo. Wire `~/.cursor-governance`, then:

```bash
make gov-pr-check
# equivalent:
make -C "$HOME/.cursor-governance" pr-check WS="$(pwd)"
```

## Architecture

- Runtime: `constellation-node-sdk` (`create_node_app` + TransportPacket)
- Makefile: Core thin facade + `Repo.mk` product targets + `gov-*` wrappers
- CI: Quantum-L9/.github via `make sync-ci` (plus local `.semgrep/` policy)
- Obs stack: optional (`make obs-up`) — not required for `make verify`

See [ARCHITECTURE.md](ARCHITECTURE.md), [TEMPLATE_INVENTORY.md](TEMPLATE_INVENTORY.md),
[docs/repository-execution-runtime.md](docs/repository-execution-runtime.md),
and [docs/agent-tasks/add-domain-handler.md](docs/agent-tasks/add-domain-handler.md).
