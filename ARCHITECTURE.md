# Architecture — l9-repo-template

Thin Python museum template for Quantum-L9.

## Layout

```
src/<pkg>/          # installable package (default: l9_example_pkg)
tests/              # smoke + automation tests
scripts/            # inventory_check, sync_ci_from_pack, bootstrap_rename, render_cursor_rules
plugin-config.yaml  # domain cartridge for Cursor rule rendering
.cursor/rules/      # templates + rendered .mdc (make render-rules)
.vscode/            # editor defaults (ruff + mypy)
.devcontainer/      # thin Python 3.12 + uv (no obs stack)
.github/            # seeded from Quantum-L9/.github (not hand-authored)
.l9/ci-pin          # ORG_GITHUB_SHA + L9_CI_CORE_PIN
```

## Org boundary

| Surface | Authority |
|---------|-----------|
| Community health (CONTRIBUTING, SECURITY, issue/PR templates) | Inherit from org `.github` |
| `l9-ci-pack` workflows + governance | Copy via `make sync-ci` |
| `templates/dependabot.yml`, `CODEOWNERS.repo` | Copy via `make sync-ci` (not inheritable) |
| LICENSE | Copy from org LICENSE SSOT |
| Product code / package rename | Local (`make rename`) |
| Cursor rule cartridge | Local (`plugin-config.yaml` + templates) |

## Force multipliers

1. `make rename PKG=foo_bar` — rewrite example identity + re-render rules
2. `make verify` — inventory + check-rules + lint + typecheck + test
3. `make sync-ci` — refresh CI from pinned org `.github` SHA
4. `make render-rules` / `make check-rules` — parametric Cursor rules

## Explicit non-goals

No FastAPI app, OTel Fix-B package, or `observability/` docker stack in this museum.
Those lived in an earlier service-template body and are rejected here to keep the template thin.
