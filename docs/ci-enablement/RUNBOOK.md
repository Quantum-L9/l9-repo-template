# RUNBOOK — CI enablement (l9-repo-template)

## For the template repo itself

- `pr-checks.yml` validates the template's config on every PR. GitGuardian runs
  once `GITGUARDIAN_API_KEY` is visible; until then it skips with a warning.
- `pr-repair.yml` is a scaffold — it intentionally fails preflight here because
  the bare template has no `L9_CI_INSTALL_SPEC`.

## For a repo created from this template

1. Install **CodeRabbit** (https://github.com/apps/coderabbitai) — `.coderabbit.yaml`
   is inherited; tune `path_instructions` to your code.
2. Set repo variable **`L9_CI_INSTALL_SPEC`** (e.g.
   `git+https://github.com/Quantum-L9/l9-ci-sdk.git@v0.1.0`) and secret
   **`SDK_TOKEN`** so `l9-ci` installs.
3. Fill **`sonar-project.properties`** (projectKey/organization/projectName),
   set `SONAR_TOKEN`, and add a Sonar job (copy the pattern from
   `l9-ci-sdk/.github/workflows/pr-checks.yml`) once you have first-party source.
4. Make `GITGUARDIAN_API_KEY` visible for the secret scan.
5. Customize `AGENT.md` (repository role, protected paths).

## Handoff to PR_Repair

`pr-repair.yml` emits `agent_review_payload.json` and, with
`dispatch=true` + `L9_IMPLEMENTER_BOT_TOKEN`, sends a `repository_dispatch`
(`l9-implementer-review`) to `Quantum-L9/PR_Repair`. The bot itself lives there,
not here. Never merge, never push, never change settings from CI.
