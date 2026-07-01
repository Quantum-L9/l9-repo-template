# CHANGE_SUMMARY — CI enablement (l9-repo-template)

## What lands

- `pr-checks.yml`: a **config-validation** gate (blocking) that checks the caller
  workflow references `Quantum-L9/l9-ci-core` + `pr-pipeline.yml` + `secrets:
  inherit`, that shipped YAML/TOML config parses, and that there are zero legacy
  references — plus GitGuardian (blocking when its secret is visible).
- `pr-repair.yml`: payload-source + PR_Repair handoff **scaffold** (bot not
  vendored); fails preflight until a consumer sets `L9_CI_INSTALL_SPEC`.
- `.coderabbit.yaml`, `sonar-project.properties` (scaffold), `AGENT.md`.

## Impact

- Repos created from this template inherit the full enablement scaffold. The
  template's own CI stays honest: it validates its config rather than running a
  non-existent test suite, and it never adds a gate that scans nothing.
- No source changes, no merges, no settings changes.

## Blocking-vs-advisory rationale

| Gate | Status today | Decision |
|---|---|---|
| template config validation | passes locally | **blocking** |
| GitGuardian | secret visibility unconfirmed | blocking when present, else skipped |
| Sonar | no first-party source in the template | scaffold only (no scan job) |
