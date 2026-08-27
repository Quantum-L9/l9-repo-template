<!-- L9_META
l9_schema: 1
origin: l9-repo-template
layer: repository
owner: platform
status: active
version: 1.1.0
updated: 2026-08-26
/L9_META -->
# Claude Operating Contract

This is a thin Claude-specific overlay. It does not replace or duplicate
`AGENTS.md`. Repository-local machine-readable contracts remain authoritative.

## Bootstrap order

1. Read `AGENTS.md`.
2. Read `.l9/architecture.yaml`, `.l9/ownership.yaml`,
   `.l9/org-birth-profile.yaml` (immutable birth record),
   `.l9/template-state.yaml` (mutable conformance state),
   `.l9/repo-workflow.json`, and `.l9/sdk-compatibility.yaml`.
3. Read `docs/WHEN_TO_USE.md` before changing product boundaries.
4. Read `docs/ops/REPO_BIRTH.md`,
   `scripts/birth-runner/payload-ownership.yaml`, and
   `scripts/birth-runner/birth_provenance.py` before changing birth behavior.
   Birth provenance is immutable; only `.l9/template-state.yaml` is reconciled.
5. Read `Repo.mk` and `pyproject.toml` before changing execution or dependency
   surfaces.

## L9 alignment law

- Preserve the declared non-Constellation product boundary. This repository is
  not the Constellation node scaffold and is not the `constellation_*`
  dependency scaffold. Those responsibilities remain with the sibling
  templates named in `.l9/architecture.yaml`.
- Extend existing surfaces. Do not create parallel runners, duplicate configs,
  duplicate agent law, or repository-local copies of centrally owned CI logic.
- A repository-shaped birth payload owns its product surfaces; do not restore
  template demo/application files that the authoritative payload omits.

## Protected behavior

- Root `Makefile` must remain byte-identical to
  `tools/l9_repo/Makefile.template`; do not hand-edit one without the other.
- Generated `.cursor/rules/*.mdc` files are renderer output; change templates or
  `plugin-config.yaml`, then render.
- If dependency resolution changes, keep `pyproject.toml` and `uv.lock`
  synchronized in the same change.
- Never add secrets, private keys, credentials, or destructive force-push
  behavior.

## CI and security ownership

- Repository-local verification belongs to `make verify` / `make ci`.
- CI execution semantics remain owned by `Quantum-L9/l9-ci-core`; organization
  CI targeting and enforcement remain centralized.
- Do not add repository-local workflow callers to work around a central CI gap.
- Shared CodeQL execution/query policy belongs outside this repository; never
  add `.github/codeql/codeql-config.yml` here.
- Repo-local `.gitleaks.toml`, Semgrep rules, pre-commit configuration, and
  CodeRabbit guidance are policy/configuration surfaces, not parallel CI engines.

## Completion contract

Before reporting a repository mutation complete:

```bash
make verify
make pr-check
pre-commit run --all-files
make agent-check
```

If a command is unavailable because its external tool is not installed, report
that fact explicitly. Do not claim any GitHub-hosted security or CI check is
green until a real hosted run has completed successfully.
