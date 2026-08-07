# Repository Execution Runtime (museum)

**Artifact:** `l9-ci-core-repository-execution-runtime`

**Version:** `4.3.1`

This template vendors Core's repository-execution runtime (`tools/l9_repo`)
at `L9_REPO_RUNTIME_PIN` and keeps the root `Makefile` byte-identical to
`tools/l9_repo/Makefile.template`.

Product force-multipliers live in `Repo.mk`. Governance stays in
Cursor-Governance and is invoked with `WS=` via `make gov-*` wrappers.

## Museum micro-patches vs upstream Core template

Kept identical between `Makefile` and `tools/l9_repo/Makefile.template`:

1. `L9_REPO` uses deferred `=` so `Repo.mk` can select `.venv/bin/python`.
2. `help` recipe lives in `Repo.mk` (lists facade + product/`gov-*` targets).

`make reconcile` rewrites `Makefile` from the vendored template (these patches).
