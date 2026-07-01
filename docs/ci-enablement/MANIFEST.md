# MANIFEST — CI enablement (l9-repo-template)

Adapted from the `l9-ci-enablement-pack` (model: `Quantum-L9/PR_Repair`). This is
a THIN template: files here are scaffolds that repos created from it inherit.

## Files

| Path | Responsibility | Consumes | Blocking? |
|---|---|---|---|
| `.github/workflows/pr-checks.yml` | Template config-validation + GitGuardian | `GITGUARDIAN_API_KEY` | config validation **blocking**; GitGuardian blocking *when secret present* |
| `.github/workflows/pr-repair.yml` | Payload source + handoff scaffold (no bot) | var `L9_CI_INSTALL_SPEC`, `SDK_TOKEN`, `L9_IMPLEMENTER_BOT_TOKEN` (opt) | n/a (manual; fails preflight until configured) |
| `.coderabbit.yaml` | CodeRabbit tuning (inherited) | app install | n/a |
| `sonar-project.properties` | Sonar SCAFFOLD (no scan job here) | `SONAR_TOKEN` (downstream) | n/a |
| `AGENT.md` | Governance contract scaffold | — | — |
| `docs/ci-enablement/*` | This pack's docs | — | — |

Adaptation notes: no `pytest` gate (no package/tests); the real quality pipeline
runs in consumer repos via `ci.yml → l9-ci-core/pr-pipeline.yml`. No Sonar scan
job (no first-party source) — the properties file is a downstream scaffold.

## Secret / variable map

| Name | Kind | Used by |
|---|---|---|
| `GITGUARDIAN_API_KEY` | secret | pr-checks / gitguardian |
| `SONAR_TOKEN` | secret | downstream Sonar |
| `SDK_TOKEN` + `L9_CI_INSTALL_SPEC` | secret + var | install `l9-ci` in consumer repos |
| `L9_IMPLEMENTER_BOT_TOKEN` | secret (optional) | cross-repo dispatch to PR_Repair |

## Unknowns (must be filled per repo — not invented)

| Where | Value | How to resolve |
|---|---|---|
| `sonar-project.properties` | projectKey/organization/projectName | from the consumer's Sonar project |
| new repo | `L9_CI_INSTALL_SPEC`, `SDK_TOKEN` | set the install spec + token in the new repo |
| PR_Repair | `on: repository_dispatch` handler | wired on the PR_Repair side |
