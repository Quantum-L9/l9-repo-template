# Template inventory

Allowed roots for this museum template. **Deny** directories must not appear at repo root.

| Path | Role | Source |
|------|------|--------|
| `.l9/ci-pin` | Org `.github` + Core SHA pins | local (museum) |
| `.l9-template-version` | Template semver | local |
| `.python-version` | Python 3.12 | local |
| `pyproject.toml` | setuptools package metadata | local (Gate_SDK shape) |
| `uv.lock` | Locked deps | local (`uv lock`) |
| `src/l9_example_pkg/` | Example package | local |
| `tests/` | Smoke + rename tests | local |
| `scripts/` | inventory / sync-ci / rename | local |
| `Makefile` | verify / sync-ci / rename | local |
| `.pre-commit-config.yaml` | Local hooks | local (Gate_SDK shape) |
| `.github/governance/` | CI governance pack | `Quantum-L9/.github` via sync-ci |
| `.github/workflows/` | l9-analysis + l9-lint-test | `Quantum-L9/.github` via sync-ci |
| `.github/dependabot.yml` | Dependabot (not inheritable) | org `templates/` via sync-ci |
| `.github/CODEOWNERS` | CODEOWNERS (not inheritable) | org `templates/CODEOWNERS.repo` via sync-ci |
| `LICENSE` | Proprietary license | org `.github` LICENSE |
| `README.md` / `AGENTS.md` / `ARCHITECTURE.md` | Docs | local |
| `requirements-consumer-ci.txt` | Consumer CI tool pins | `l9-ci-core` (if pack lacks) |

## Inherit (do not copy)

Community health from [Quantum-L9/.github](https://github.com/Quantum-L9/.github): `CONTRIBUTING`, `SECURITY`, `SUPPORT`, `CODE_OF_CONDUCT`, `FUNDING`, issue/PR templates.

## Deny at repo root

`engine/`, `chassis/`, `domains/`, `client/`, `database/`, `deploy/`, `observability/`, `example_service/`, `tools/`

## Forbidden

- Org `workflow-templates/*` (v1 starters)
- Org `rulesets/`, `ops/`, `profile/`, org-only workflows
- Golden-repo kitchen-sink CI / Poetry / Sonar / PacketEnvelope
