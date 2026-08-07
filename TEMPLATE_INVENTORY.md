# Template inventory

| Path | Role | Source |
|------|------|--------|
| `.l9/ci-pin` | Org / Core workflow / Gate_SDK / runtime pins | local |
| `Makefile` | Core thin facade (byte-identical to template) | l9-ci-core `L9_REPO_RUNTIME_PIN` |
| `Repo.mk` | Product targets + `gov-*` WS= wrappers | museum |
| `tools/l9_repo/` | Repository-execution runtime | l9-ci-core vendored |
| `.l9/repo-workflow.json` + schema | agent-check matrices | museum (Core schema) |
| `MANIFEST.sha256` | Runtime surface checksums | regenerated locally |
| `src/<pkg>/app.py` + `handlers.py` | Worker shell | Gate_SDK example adapted |
| `spec.yaml` | Gate registration | Gate_SDK example adapted |
| `Dockerfile` / `docker-compose.yml` | uv api runtime | golden shape, uv rewrite |
| `scripts/wait_for_http.py` | readiness poll | golden idea |
| `scripts/preflight_local_env.py` | local env check | golden preflight idea (local only) |
| `observability/` | Optional local obs stack | constellation-file-inventory |
| `.semgrep/semgrep-rules.yaml` | Semgrep policy | golden adapted |
| `docs/examples/` | CodeRabbit + SLO extras | golden surgical |
| `plugin-config.yaml` + `.cursor/` | Parametric rules | file-inv DX |
| `.github/` | CI pack | Quantum-L9/.github via sync-ci |

## Inherit

CONTRIBUTING / SECURITY / issue+PR templates from org `.github`.

## Deny at repo root

`engine/`, `chassis/`, `domains/`, `client/`, `database/`, `deploy/`, `example_service/`

`tools/` is **allowed only** for `tools/l9_repo/` + `tools/check_workflow_integrity.py`.

`observability/` is **allowed** as opt-in local pack (not required for verify).

## Rejected

PacketEnvelope, Poetry, Sonar, golden parallel CI/SBOM/SLSA, golden Loki/Alloy stacks,
file-inv Fix-B OTel Python, Justfile dual runner, copying Cursor-Governance Makefile/ops.
