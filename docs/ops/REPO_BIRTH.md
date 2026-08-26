# Repo birth (non-Constellation)

```bash
make new-repo \
  REPO=l9-observability-core \
  PKG=l9_observability_core \
  DESC="Canonical backend-neutral observability domain contracts" \
  PAYLOAD=/path/to/l9-observability-core
```

When that returns **PASS** the repository is born. Not "created, now go do
seven other things".

## What `make new-repo` guarantees

One command executes one state machine. Every stage passes or the birth stops.

```
make new-repo
      │
      ▼
[1] PREFLIGHT              git / gh / uv · auth · repo-name + package validation
                           · target repo does not already exist
      ▼
[2] ASSEMBLE LOCALLY       current l9-repo-template · rename/stamp identity
                           · optional product PAYLOAD · payload ownership
      ▼
[3] FINALIZE               canonical LICENSE · uv lock · render generated rules
   AUTOMATICALLY           · regenerate manifests · normalize metadata
      ▼
[4] APPLY ORG BIRTH        current Quantum-L9/.github · only applicable
    PROFILE                non-inheritable controls · current org SHA recorded
      ▼
[5] VALIDATE BEFORE        inventory · hygiene · rules · lint · format
    CREATION               · typecheck · tests · uv lock --check
      ▼
[6] CREATE GITHUB REPO     create remote · push finalized initial repository
      ▼
[7] REMOTE ORG BOOTSTRAP   labels · repo settings · applicable seeding
      ▼
[8] REMOTE ATTESTATION     read the actual remote back · verify org profile
                           · verify required files · verify HEAD
      ▼
BIRTH: PASS
```

`uv lock` is stage 3. It is not something a product author is asked to
remember; it is a birth invariant, and a birth invariant belongs to the birth
engine.

**Nothing is created until stage 5 is green.** A failed test does not leave a
half-born repository on GitHub — it leaves a work directory and a receipt.

## Parameters

| Variable | Required | Meaning |
|----------|----------|---------|
| `REPO` | yes | GitHub repository name |
| `PKG` | yes | snake_case Python package name |
| `DESC` | yes | one-line description |
| `PAYLOAD` | no | product files. A fragment is overlaid (payload wins on collision); a whole repository is **authoritative** — see below |
| `ORG` | no | GitHub owner (default `Quantum-L9`) |
| `WORK_DIR` | no | where the repository is assembled (default `/tmp/l9-births`) |
| `CLASS` | no | org repo class (default `non_constellation_python`) |
| `ORG_PROFILE_SRC` | no | local `Quantum-L9/.github` checkout — skips the `gh` read, enables an offline birth |
| `RECEIPT` | no | where to write the birth receipt JSON |
| `PRIVATE` | no | create the repository private |
| `NO_REMOTE` | no | stop after stage 5 — assemble, finalize, and validate only |

## What a PAYLOAD owns

`PAYLOAD` has two modes, and which one applies is decided by the payload's
shape, never by a flag.

| Payload | Mode | Absence means |
|---------|------|---------------|
| a fragment — some files, part of a tree | **additive overlay** | nothing. The template keeps everything the payload does not mention. |
| a standalone repository | **authoritative** | the product does not own that surface. It is removed. |

A payload is repository-shaped when it carries every path in
`repository_shape` — today `pyproject.toml`, `.l9/architecture.yaml`, `src/`,
`tests/`, and `scripts/inventory_check.py`. Identification is positive: a large
payload, or one that merely happens to have a `src/` directory, stays additive.

This exists because an overlay can only ever *overwrite*. It cannot say "this
product has no Dockerfile", because there is no file in the payload with which
to say it. Without the authoritative mode, a repository of backend-neutral
domain contracts is born carrying the template's FastAPI service, its Docker
runtime, and its local observability stack — not because anyone asked for them,
but because nothing in the payload had the same name.

What survives an authoritative payload is declared in
`scripts/birth-runner/payload-ownership.yaml`, which splits this template's own
surfaces two ways:

| List | Contents | Under an authoritative payload |
|------|----------|-------------------------------|
| `chassis` | the birth engine, the repository-execution facade, `tools/`, generated-rule templates, the canonical LICENSE, org metadata | always kept; a payload may still overwrite an individual file |
| `product` | the example product — `src/**`, `tests/**`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `observability/**`, `docs/examples/**` | kept only where the payload supplies it |

Organization surfaces are not listed there at all: stage 4 MATERIALIZE decides
those, and birth does not get a second opinion. A product owns its product, not
the factory that made it.

Two consequences worth stating plainly:

- The payload's package **replaces** the renamed template package. It is not
  union-merged with it, so `app.py`, `settings.py`, `health.py`, `protocols.py`
  and `retry.py` do not reappear as if the product had written them.
- `PKG` must name the package the payload ships. A mismatch stops the birth in
  stage 2 rather than surfacing as an import error in stage 5.

Every path this template tracks must appear in one of the two lists; a unit test
enforces it. Adding a file to this template therefore forces an answer to "does
a product inherit this?" instead of defaulting to yes.

## The org birth profile

Stage 4 reads `policies/repo-classes.yml` from `Quantum-L9/.github` at its
current SHA and applies the class this repository declares in
`.l9/org-birth-profile.yaml`. The organization contract has four modes:

| Mode | Meaning |
|------|---------|
| **INHERIT** | GitHub supplies it org-wide; the repository must not carry a copy |
| **MATERIALIZE** | the repository must contain the file |
| **REMOTE APPLY** | GitHub API state, not a file (labels, settings) |
| **FORBID** | the repository must never carry this path |

`FORBID` is not only a filter on the organization's seed payload — it is an
assertion about the assembled tree, checked before creation. A product
`PAYLOAD` that ships `.github/workflows/l9-analysis.yml` stops the birth in
stage 4 with a named violation, because organization CI targeting belongs to
`l9-ci-core` / `l9-ci-control-plane` and never to the repository.

This is what keeps a beautiful automation machine from automatically punching
itself in the face: the organization seeder's historic default categories write
11 paths that this template's `scripts/inventory_check.py` fails closed on.
Class-aware seeding means the newborn is given applicable *capabilities*, not
all files.

See `docs/REPO_BIRTH_PROFILES.md` in `Quantum-L9/.github` for the contract.

## The birth receipt

Every run writes `<WORK_DIR>/<REPO>-birth-receipt.json` — the two provenance
SHAs (template and organization), the resolved class, and per-stage results.
The same two SHAs are committed into the newborn's `.l9/org-birth-profile.yaml`,
so a repository can always answer *which pair of commits was I born from*.

## Ownership

```
l9-repo-template      owns HOW A REPO IS BORN
Quantum-L9/.github    owns WHAT THE ORGANIZATION REQUIRES
l9-ci-core            owns HOW CI EXECUTES
l9-ci-control-plane   owns WHICH CI APPLIES WHERE
the product repo      owns ITS PRODUCT
```

No duplicated authority. This template never decides what the organization
requires; it reads the contract at a recorded SHA and applies it.

## Manual path

Still supported, and still what the stages automate:

1. Use template: `Quantum-L9/l9-repo-template`
2. Clone the new repo
3. `make rename PKG=your_pkg`
4. `make verify`
5. Push your feature branch; open the PR via Cursor-Governance (`make gov-pr`)

In-repo gates never open PRs (`OPEN_PR=0`).

## Staged runner (debugging surface)

The original four-stage runner remains for debugging an individual stage. It
does **not** apply the org birth profile and does not attest the remote — use
`make new-repo` for a real birth.

```bash
export PLAY_DIR=/tmp/museum-birth-demo
mkdir -p "$PLAY_DIR"
cp scripts/birth-runner/config.template.yaml "$PLAY_DIR/config.yaml"
# edit config.yaml: org, repo_name, package_name, description, work_dir
bash scripts/birth-runner/01_preflight.sh
bash scripts/birth-runner/02_bootstrap.sh
bash scripts/birth-runner/03_verify.sh
PUSH=1 bash scripts/birth-runner/04_push.sh   # optional, explicit
```

No PackageTemplate plays catalog. No Gate-worker birth framing.
