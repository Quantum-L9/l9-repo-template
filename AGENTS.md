# AGENTS.md — L9 Gate worker template

## Mission (fill in)

Gate-routed worker node. Express intent by `action`; Gate resolves destinations.
Drop domain logic into `handlers.py`.

## Owns

- Worker package under `src/` (`app.py`, `handlers.py`, `spec.yaml`)
- Local verify + Cursor rule drift + optional local obs stack
- CI sync from org pack (`make sync-ci`)
- Product Make targets in `Repo.mk`

## Authority contracts

- [`.l9/architecture.yaml`](.l9/architecture.yaml)
- [`.l9/ownership.yaml`](.l9/ownership.yaml)
- [`.l9/sdk-compatibility.yaml`](.l9/sdk-compatibility.yaml)

## Never

- Peer URL dispatch or `PacketEnvelope`
- `engine/`, `chassis/`, `domains/`, Poetry, Sonar, golden parallel CI
- Hand-editing `.github/workflows/*` — re-run `make sync-ci`
- Hand-editing generated `.cursor/rules/*.mdc`
- Copying Cursor-Governance Makefile/ops into this repo
- Requiring `make obs-up` for verify/CI
- Editing root `Makefile` by hand — it must match `tools/l9_repo/Makefile.template` (`make reconcile`)

## Agent completion contract

1. Product green: `make verify` (or `make pr-check`)
2. When Cursor-Governance is wired: `make gov-pr-check`
3. Prefer `make gov-pr` to open/remediate PRs — in-repo `OPEN_PR` stays `0`
4. Optional Core facade proof: `make agent-check`

## Validation ladder

```bash
make inventory-check
make check-rules
make lint
make typecheck
make test
# or: make verify
```

## Governance control plane (WS=)

CG changes propagate as shared tooling when consumers call CG with `WS=`.
This template exposes thin wrappers only:

```bash
make gov-pr-check
make gov-pr
make gov-start
make gov-wiring-check
```

Equivalent explicit form:

```bash
make -C "$HOME/.cursor-governance" pr-check WS="$(pwd)"
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

Pins: `.l9/ci-pin` (`ORG_GITHUB_SHA`, `L9_CI_CORE_PIN`, `GATE_SDK_SHA`, `L9_REPO_RUNTIME_PIN`).
