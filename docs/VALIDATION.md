# Validation honesty

What green means for this non-Constellation Python template.

| Gate | Command | Proves |
|------|---------|--------|
| Inventory | `make inventory-check` | Required baseline files, deny dirs, no Gate-worker defaults, tools allowlist, agent/security discovery wiring, birth-profile and payload-ownership presence |
| Hygiene | `make hygiene-check` | No eval/exec/print in `src/`; no Justfile/contracts/enginehandlers reintro |
| Birth integrity | `make birth-check` | This repository is what its birth record claims: receipt digest, provenance files, root-commit trailers, and the contents digest all agree. An UNBORN repository (no `.l9/birth-receipt.json`) passes |
| Pre-commit | `pre-commit run --all-files` | Generic file hygiene plus Ruff/mypy and local L9 checks |
| Gitleaks policy | `gitleaks git --config .gitleaks.toml --no-banner --redact .` | Gitleaks default detection corpus is active with repo-local configuration when the scanner is available |
| Semgrep policy | `semgrep --config .semgrep/semgrep-rules.yaml .` | Generic repo-local high-signal Python security rules |
| Cursor rules | `make check-rules` | Rendered `.mdc` matches templates + `plugin-config.yaml` |
| Lint / types | `make lint` / `make typecheck` | Ruff + mypy |
| Tests | `make test` | Unit + integration |
| Product | `make verify` / `make pr-check` | Full local ladder (`OPEN_PR=0`) |
| Core facade | `make agent-check` | Vendored `tools.l9_repo` completion proof |
| Governance | `make gov-pr-check` | Cursor-Governance against `WS=$(pwd)` when wired |

The root `bootstrap.sh` delegates to the existing `tools.l9_repo setup` command;
it does not create a second bootstrap implementation. Repo-local security
configuration does not imply repo-local CI ownership.

## What green does **not** prove

- Constellation transport / Gate routing correctness (belongs to L9-Node-Template / Gate_SDK)
- `constellation_*` dependency birth (belongs to PackageTemplate)
- Production observability (optional `make obs-up` is local compose only)
- GitHub-hosted CodeQL or other organization CI execution; that requires an actual hosted run targeted by the central control plane
- Presence of a local Gitleaks or Semgrep binary unless those commands were actually executed
- Database migration readiness; Alembic is a downstream database-capability cartridge, not base-template infrastructure
- **Current conformance.** `make birth-check` proves where a repository came from, not whether it has drifted from today's required org/template state. Drift is `.l9/template-state.yaml` against a per-class desired state, answered centrally — see [ops/REPO_BIRTH.md](ops/REPO_BIRTH.md)
- That this repo should be used for nodes or dependency packages — see [WHEN_TO_USE.md](WHEN_TO_USE.md)
