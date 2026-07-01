# VALIDATION — CI enablement (l9-repo-template)

Local evidence before opening the PR.

## Blocking gate — template config validation

```
$ python  # the pr-checks template-validation step, run locally
template config OK
```

Checks performed: `ci.yml` references `Quantum-L9/l9-ci-core`, `pr-pipeline.yml`,
and `secrets: inherit`; `ci.yml` + `.pre-commit-config.yaml` parse as YAML;
`pyproject.toml` + `.gitleaks.toml` parse as TOML; zero legacy references in the
repo (the forbidden tokens are assembled from fragments so the guard file itself
does not contain them).

```
$ grep -RIn "<legacy tokens>" . --exclude-dir=.git --exclude-dir=.ruff_cache
OK: zero literal tokens
```

## Workflow structure

`pr-checks.yml` and `pr-repair.yml` parse as YAML with `on`, `permissions`,
`jobs`, and steps in every job.

## Secret / fork safety

- `gitguardian` is same-repo only and detects its secret; skips when absent.
- No `pull_request_target`. No secrets committed (diff grepped).

## Unknowns confirmed labeled

`sonar.projectKey`/`organization`/`projectName` = `UNKNOWN_…`; per-repo
`L9_CI_INSTALL_SPEC`/`SDK_TOKEN` and the PR_Repair dispatch handler in MANIFEST.md.
