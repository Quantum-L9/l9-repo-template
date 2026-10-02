# l9-repo-template

Generic **Quantum-L9 repository birth factory**. This repository owns *how* an
L9 repository is born — deterministic assembly, compiled-payload verification,
birth provenance, local validation, publication of the sealed root, invocation
of organization-owned bootstrap, and remote attestation.

It does **not** own *what* semantic product is born. ProductTopology,
ProductManifest, ProductKind and archetype semantics are upstream inputs owned
by [`Quantum-L9/.github`](https://github.com/Quantum-L9/.github) `semantics/`
and the product's semantic owner. The Python/FastAPI content shipped here is a
reference payload that demonstrates the chassis — see
[docs/WHEN_TO_USE.md](docs/WHEN_TO_USE.md).

## Quick start

```bash
make new-repo \
  REPO=l9-observability-core \
  PKG=l9_observability_core \
  DESC="Canonical backend-neutral observability domain contracts" \
  PAYLOAD=/path/to/l9-observability-core
```

When that returns **PASS** the repository is born — identity stamped, `uv.lock`
resolved, the current `Quantum-L9/.github` birth profile applied, the full gate
green, the repository created and pushed, org labels and settings applied, and
the remote read back and attested. Nothing is created until validation passes.

See [docs/ops/REPO_BIRTH.md](docs/ops/REPO_BIRTH.md) for the stages and
every parameter.

## Manual path

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
| Birth | `make new-repo` | One-command repository birth |
| Product | `make verify` / `make pr-check` | In-repo chassis gate (`OPEN_PR=0`) |
| Core facade | `make agent-check` / `make validate` | Vendored `tools.l9_repo` completion proof |
| Governance | `make gov-pr-check` | Cursor-Governance via `WS=$(pwd)` |

```bash
make gov-pr-check
# equivalent:
make -C "$HOME/.cursor-governance" pr-check WS="$(pwd)"
```

## Architecture

- Factory role: repository birth only; product semantics arrive resolved from upstream
- Reference payload: minimal FastAPI hello (example, not factory law)
- Makefile: Core thin facade + `Repo.mk` product targets + `gov-*` wrappers
- CI: org control plane (l9-ci-core execution, l9-ci-control-plane targeting) — no repo-side sync
- Org birth profile: this repo declares its own class in `.l9/org-birth-profile.yaml`
  (`non_constellation_python`, an organization birth class, not a ProductKind);
  `Quantum-L9/.github` decides what that class receives
- Obs stack: optional (`make obs-up`) — not required for `make verify`

See [ARCHITECTURE.md](ARCHITECTURE.md), [TEMPLATE_INVENTORY.md](TEMPLATE_INVENTORY.md),
and [docs/WHEN_TO_USE.md](docs/WHEN_TO_USE.md).
