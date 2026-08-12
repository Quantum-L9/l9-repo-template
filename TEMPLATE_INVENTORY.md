# Template inventory

Allowed roots for this museum template. **Deny** directories must not appear at repo root.

| Path | Role | Source |
|------|------|--------|
| `.l9/ci-pin` | Org `.github` + Core SHA pins | local (museum) |
| `.l9-template-version` | Template semver | local |
| `.python-version` | Python 3.12 | local |
| `pyproject.toml` | setuptools package metadata | local (Gate_SDK shape) |
| `uv.lock` | Locked deps | local (`uv lock`) |
| `plugin-config.yaml` | Domain cartridge for Cursor rules | adapted from constellation-file-inventory |
| `src/l9_example_pkg/` | Example package | local |
| `tests/` | Smoke + automation tests | local |
| `scripts/` | inventory / sync-ci / rename / render-rules | local + file-inv renderer |
| `Makefile` | verify / sync-ci / rename / render-rules | local + file-inv DX |
| `.pre-commit-config.yaml` | Local hooks (mypy, not pyright) | local + file-inv hooks |
| `.cursor/rules/templates/` | Parametric `.mdc.template` | adapted from file-inv (no fastapi) |
| `.cursor/rules/*.mdc` | Rendered rules | `make render-rules` |
| `.vscode/` | Editor settings | adapted from file-inv (ruff + mypy) |
| `.devcontainer/` | Thin Python 3.12 + uv | adapted from file-inv (no obs ports) |
| `.github/governance/` | CI governance pack | `Quantum-L9/.github` via sync-ci |
| `.github/workflows/` | l9-analysis + l9-lint-test + governance | `Quantum-L9/.github` via sync-ci |
| `.github/dependabot.yml` | Dependabot (not inheritable) | org `templates/` via sync-ci |
| `.github/CODEOWNERS` | CODEOWNERS (not inheritable) | org `templates/CODEOWNERS.repo` via sync-ci |
| `.github/labels.yml` | Org-standard label definitions | org `templates/` via sync-ci |
| `.github/ISSUE_TEMPLATE/` | Issue forms (bug, feature, task, incident, ci-failure, gov-violation) | org `templates/issue-templates/` via sync-ci |
| `.github/pull_request_template.md` | PR template with gates checklist | org `templates/pr-templates/` via sync-ci |
| `.github/FUNDING.yml` | Org funding config | org `templates/community-health/` via sync-ci |
| `CODE_OF_CONDUCT.md` | Org code of conduct | org `templates/community-health/` via sync-ci |
| `CONTRIBUTING.md` | Org contributing guide | org `templates/community-health/` via sync-ci |
| `SECURITY.md` | Org security policy | org `templates/community-health/` via sync-ci |
| `SUPPORT.md` | Org support channels | org `templates/community-health/` via sync-ci |
| `LICENSE` | Proprietary license | org `templates/community-health/` via sync-ci |
| `README.md` / `AGENTS.md` / `ARCHITECTURE.md` | Docs | local |
| `docs/PARAMETRIC_CURSOR_RULES.md` | Renderer usage | adapted from file-inv |
| `requirements-consumer-ci.txt` | Consumer CI tool pins | `l9-ci-core` via sync-ci |

## Seeded by `make sync-ci` (full list)

All of the following are pulled from `Quantum-L9/.github` at the SHA pinned in
`.l9/ci-pin` (`ORG_GITHUB_SHA`). Consumer CI requirements come from
`Quantum-L9/l9-ci-core` at `L9_CI_CORE_PIN`.

| Category | Org source path | Consumer destination |
|----------|-----------------|---------------------|
| Governance | `l9-ci-pack/governance/*.yaml` | `.github/governance/` |
| CI workflows | `l9-ci-pack/workflows/l9-*.yml` | `.github/workflows/` |
| CODEOWNERS | `templates/CODEOWNERS.repo` | `.github/CODEOWNERS` |
| Dependabot | `templates/dependabot.yml` | `.github/dependabot.yml` |
| Governance caller | `templates/governance-caller.yml` | `.github/workflows/governance.yml` |
| Labels | `templates/labels.yml` | `.github/labels.yml` |
| Community health | `templates/community-health/*` | repo root + `.github/FUNDING.yml` |
| Issue templates | `templates/issue-templates/*` | `.github/ISSUE_TEMPLATE/` |
| PR template | `templates/pr-templates/pull_request_template.md` | `.github/pull_request_template.md` |
| CI tool pins | (from l9-ci-core) `requirements-consumer-ci.txt` | `requirements-consumer-ci.txt` |

## Deny at repo root

`engine/`, `chassis/`, `domains/`, `client/`, `database/`, `deploy/`, `observability/`, `example_service/`, `tools/`

## Rejected ports from constellation-file-inventory

| Surface | Why rejected |
|---------|----------------|
| FastAPI `src/l9_service` + OTel Fix-B | Kitchen-sink; museum stays thin |
| `observability/` compose stack | Deny-class fat DX |
| `ci.yml` / `pr-pipeline.yml` / gitleaks / dependency-review / auto-merge | Org pack + `make sync-ci` only |
| hatchling / pyright / cov-fail 70 | Museum: setuptools + mypy + org `COVERAGE_THRESHOLD=0` |
| `fastapi.mdc.template` / Justfile / MANIFEST checksum table | Not default museum; inventory covers sources |

## Forbidden

- Org `workflow-templates/*` (v1 starters)
- Org `rulesets/`, `ops/`, `profile/`, org-only workflows
- Golden-repo kitchen-sink CI / Poetry / Sonar / PacketEnvelope
