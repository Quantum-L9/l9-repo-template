# Contributing to Quantum-L9

## Governance Setup Checklist {#governance-setup}

Before opening any pull request, verify each item:

- [ ] Cloned `Cursor-Governance` into your local workspace root
- [ ] Ran `setup_workspace_symlinks.sh` (see [§2 symlink contract](https://github.com/Quantum-L9/Cursor-Governance/blob/main/CANONICAL_LAW.md#2-symlink-contract))
- [ ] Validated symlinks resolve correctly: `ls -la .cursor/rules .cursor/skills .cursor/commands`
- [ ] Read [CANONICAL_LAW.md §8](https://github.com/Quantum-L9/Cursor-Governance/blob/main/CANONICAL_LAW.md#8) for workspace wiring requirements
- [ ] Reviewed [CANONICAL_LAW.md §7 Anti-Patterns](https://github.com/Quantum-L9/Cursor-Governance/blob/main/CANONICAL_LAW.md#7-anti-patterns) — never violate these
- [ ] All CI gates green (no bypassing required status checks)
- [ ] CODEOWNERS notified for blast-radius files

---

## Quick Setup (3 Steps)

```bash
# Step 1: Clone Cursor-Governance alongside your target repo
git clone https://github.com/Quantum-L9/Cursor-Governance.git

# Step 2: Run workspace symlink wiring
cd Cursor-Governance
bash scripts/setup_workspace_symlinks.sh

# Step 3: Validate symlinks
ls -la .cursor/rules .cursor/skills .cursor/commands
# Expected: all three resolve without error
```

Per [CANONICAL_LAW.md §2](https://github.com/Quantum-L9/Cursor-Governance/blob/main/CANONICAL_LAW.md#2-symlink-contract):
the workspace root must have `.cursor/` symlinks resolving to `Cursor-Governance/rules/`, `skills/`, and `commands/`.

---

## CI Gate Requirements

All pull requests must pass the repository-local validation ladder before
merge:

| Gate | Tool | Surface |
|---|---|---|
| Inventory + hygiene | `scripts/inventory_check.py`, `repo_hygiene_audit.py` | `make verify` / `make ci` |
| Cursor-rule drift | `render_cursor_rules.py --check` | `make verify` / `make ci` |
| Lint + format | ruff check / format --check | `make verify` / `make ci` |
| Type-check | mypy src | `make verify` / `make ci` |
| Unit + integration tests | pytest | `make verify` / `make ci` |
| Lock consistency | `uv lock --check` | `make pr-check` |

CI execution semantics are owned by l9-ci-core and organization CI
targeting by l9-ci-control-plane; this repository does not ship
organization workflow files (see `.l9/architecture.yaml` `ci_ownership`).

---

## Branch Naming & Commit Conventions

- Branches: `feat/<scope>`, `fix/<scope>`, `chore/<scope>`, `docs/<scope>`
- Commits: Conventional Commits format — `feat(scope): message`
- PRs targeting `main` require 2 CODEOWNERS approvals for blast-radius paths

---

## This Repo's Own CI

`Quantum-L9/.github` validates itself on every PR/push to `main` — note that
none of the 12 files under `workflow-templates/` ever run as CI *in this
repo*; they only appear as starter-workflow choices in other repos' Actions
tab. What actually executes here:

- **`validate-starters.sh`** — workflow-templates + `l9-ci-pack/` completeness
  and `@main`-ref check (existing).
- **`actionlint`** — lints every file in `workflow-templates/` and
  `l9-ci-pack/workflows/` for YAML/expression/shellcheck errors
  ([`.github/workflows/actionlint.yml`](.github/workflows/actionlint.yml)).
- **`SHA-pin audit`** — repo-wide: every `uses:` ref in `workflow-templates/`,
  `l9-ci-pack/workflows/`, and `.github/workflows/` must be pinned by full
  40-char commit SHA, except the documented frozen `Quantum-L9/l9-ci-core`
  tags (`@v1` legacy, `@v2`/`@v2.0.0` current)
  ([`ops/audit-sha-pins.sh`](ops/audit-sha-pins.sh)).
- **`properties.json schema validation`** — every
  `workflow-templates/*.properties.json` against
  [`ops/schemas/workflow-template-properties.schema.json`](ops/schemas/workflow-template-properties.schema.json).
  This is a structural schema only — `categories` is deliberately
  unconstrained by an enum. GitHub's real category vocabulary is an open
  union (11 fixed buckets + any [linguist](https://github.com/github/linguist/blob/main/lib/linguist/languages.yml)
  language + tech-stack names) with no single closed list; the community
  SchemaStore schema for this file type encodes only the linguist-language
  list and would false-flag legitimate buckets like `Automation` or
  `continuous-integration`.
- **SonarCloud** — external GitHub App, not a workflow file, always runs.

---

## Kernel Authoring (l9-ci-core contributors only)

- Kernels must use `on: workflow_call` only
- `l9-self-ci.yml` must remain `on: pull_request/push` — **never convert to workflow_call** (circular dependency)
- `@v1` moving tag discipline: force-update `v1` for backward-compatible changes; cut `v2` for breaking changes
- See [workflow-interface-registry.yml](https://github.com/Quantum-L9/.github/blob/main/workflow-interface-registry.yml) for the full kernel API contract
