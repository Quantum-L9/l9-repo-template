# AGENTS.md — L9 repo template

Operating stub for coding agents. Replace the mission section when deriving a product repo via `make rename`.

## Mission (fill in)

This repository is a thin L9 Python GitHub Template. Derived repos should state:

- what the package owns
- what it never owns (routing authority, peer dispatch, etc. — product-specific)

## Owns

- Example package under `src/` (rename with `make rename PKG=...`)
- Local verify surface: lint, typecheck, tests, inventory
- CI sync from org pack (`make sync-ci`)

## Never

- Peer URL dispatch or alternate transport contracts (product repos: follow your domain AGENTS)
- Re-authoring org-inheritable community health files
- Hand-editing `.github/workflows/*` copied from the pack — re-run `make sync-ci`
- Introducing `engine/`, `chassis/`, `domains/`, or golden-repo kitchen-sink layout

## Validation

```bash
make verify
```

## CI (from Quantum-L9/.github via sync-ci)

| Workflow | Trigger | Role |
|----------|---------|------|
| `l9-lint-test.yml` | PR, push `main`, dispatch | ruff / mypy / pytest |
| `l9-analysis.yml` | PR, dispatch | semgrep + Core governance publish |

Pins live in `.l9/ci-pin`. Bump CI by updating the pin and running `make sync-ci`.
