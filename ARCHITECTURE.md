# Architecture — l9-repo-template

Thin Python museum template for Quantum-L9.

## Layout

```
src/<pkg>/          # installable package (default: l9_example_pkg)
tests/              # smoke + automation tests
scripts/            # inventory_check, sync_ci_from_pack, bootstrap_rename
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

## Force multipliers

1. `make rename PKG=foo_bar` — rewrite example identity
2. `make verify` — inventory + lint + typecheck + test
3. `make sync-ci` — refresh CI from pinned org `.github` SHA
