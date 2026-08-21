<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-repo-template
path: CLAUDE.md
layer: repository
owner: platform
status: active
version: 1.0.0
updated: 2026-08-21
/L9_META -->
# Claude Operating Contract

This is a thin Claude-specific overlay. It does not replace or duplicate
`AGENTS.md`. Repository-local machine-readable contracts remain authoritative.

## Bootstrap order

1. Read `AGENTS.md`.
2. Read `.l9/architecture.yaml`, `.l9/ownership.yaml`,
   `.l9/repo-workflow.json`, and `.l9/sdk-compatibility.yaml`.
3. Read `docs/WHEN_TO_USE.md` before changing template product boundaries.
4. Read `Repo.mk` and `pyproject.toml` before changing execution or dependency
   surfaces.

## L9 alignment law

- Treat this repository as an L9 organization template that is aligned to the
  Constellation at governance, CI, security, and interface boundaries.
- Preserve its declared product boundary: this repository is not the
  Constellation node scaffold and is not the `constellation_*` dependency
  scaffold. Those responsibilities remain with the sibling templates named in
  `.l9/architecture.yaml`.
- Extend existing surfaces. Do not create parallel runners, duplicate configs,
  duplicate agent law, or repository-local copies of centrally owned CI logic.

## Protected behavior

- Root `Makefile` must remain byte-identical to
  `tools/l9_repo/Makefile.template`; do not hand-edit one without the other.
- Generated `.cursor/rules/*.mdc` files are renderer output; change templates or
  `plugin-config.yaml`, then render.
- If dependency resolution changes, keep `pyproject.toml` and `uv.lock`
  synchronized in the same change.
- Never add secrets, private keys, credentials, or destructive force-push
  behavior to the template.

## CI and CodeQL ownership

- Repository-local verification belongs to `make verify` / `make ci`.
- CI execution semantics remain owned by `Quantum-L9/l9-ci-core`; organization
  CI control remains centralized.
- CodeQL query policy and reusable execution are centralized in
  `Quantum-L9/Cursor-Governance`.
- Keep `.github/workflows/codeql.yml` as the sanctioned thin caller.
- Never add `.github/codeql/codeql-config.yml` here. A local copy would fork the
  organization source of truth.

## Completion contract

Before reporting a repository mutation complete:

```bash
make verify
make pr-check
pre-commit run --all-files
make agent-check
```

If a command is unavailable because its external tool is not installed, report
that fact explicitly. Do not claim GitHub-hosted CodeQL is green until a real
Actions run has completed successfully.
