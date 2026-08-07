# AGENTS.md — L9 Gate worker template

## Mission (fill in)

Gate-routed worker node. Express intent by `action`; Gate resolves destinations.
Drop domain logic into `handlers.py`.

## Owns

- Worker package under `src/` (`app.py`, `handlers.py`, `spec.yaml`)
- Local verify + Cursor rule drift + optional local obs stack
- CI sync from org pack (`make sync-ci`)

## Never

- Peer URL dispatch or `PacketEnvelope`
- `engine/`, `chassis/`, `domains/`, Poetry, Sonar, golden parallel CI
- Hand-editing `.github/workflows/*` — re-run `make sync-ci`
- Hand-editing generated `.cursor/rules/*.mdc`
- Requiring `make obs-up` for verify/CI

## Validation ladder

```bash
make inventory-check
make check-rules
make lint
make typecheck
make test
# or: make verify
```

## Domain drop-in

See [docs/agent-tasks/add-domain-handler.md](docs/agent-tasks/add-domain-handler.md).

## Secret rotation

See [docs/ops/SECRET_ROTATION_CHECKLIST.md](docs/ops/SECRET_ROTATION_CHECKLIST.md).

## CI (org pack via sync-ci)

| Workflow | Role |
|----------|------|
| `l9-lint-test.yml` | ruff / mypy / pytest |
| `l9-analysis.yml` | semgrep (+ `.semgrep/semgrep-rules.yaml`) + Core publish |

Pins: `.l9/ci-pin` (`ORG_GITHUB_SHA`, `L9_CI_CORE_PIN`, `GATE_SDK_SHA`).
