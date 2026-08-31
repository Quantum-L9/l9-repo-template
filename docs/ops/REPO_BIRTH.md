# Repo birth (non-Constellation)

```bash
# [0] compile the payload from a clean checkout of the actual source repository
make birth-payload \
  SOURCE=/path/to/l9-observability-core \
  OUT=/tmp/l9-observability-core.payload.json

# [1..9] birth, authorized by that compiled payload
make new-repo \
  REPO=l9-observability-core \
  PKG=l9_observability_core \
  DESC="Canonical backend-neutral observability domain contracts" \
  PAYLOAD=/path/to/l9-observability-core \
  PAYLOAD_CONTRACT=/tmp/l9-observability-core.payload.json
```

A fragment payload needs no contract — see [What a PAYLOAD owns](#what-a-payload-owns).

When that returns **PASS** the repository is born. Not "created, now go do
seven other things".

## What `make new-repo` guarantees

One command executes one state machine. Every stage passes or the birth stops.

```
make birth-payload
      │
      ▼
[0] COMPILE PAYLOAD        clean git source · pin source SHA + tree · inventory
                           actual files · reject engine-owned paths · derive
                           repository shape and package identity · hash every
                           file · emit l9.birth-payload/v1
      │
      ▼
make new-repo
      │
      ▼
[1] PREFLIGHT              git / gh / uv · auth · repo-name + package validation
                           · target repo does not already exist · recompute the
                           source manifest and require the compiled digest
      ▼
[2] ASSEMBLE LOCALLY       current l9-repo-template · rename/stamp identity
                           · optional product PAYLOAD · payload ownership
      ▼
[3] FINALIZE               canonical LICENSE · uv lock · reconcile plugin-config
   AUTOMATICALLY           · render generated rules · regenerate manifests
      ▼
[4] APPLY ORG BIRTH        current Quantum-L9/.github · only applicable
    PROFILE                non-inheritable controls · current org SHA recorded
      ▼
[5] STAMP BIRTH            .l9-template-version · .l9/org-birth-profile.yaml
    PROVENANCE             · .l9/birth-receipt.json · .l9/template-state.yaml
      ▼
[6] VALIDATE BEFORE        inventory · hygiene · birth integrity · rules · lint
    CREATION               · format · typecheck · tests · uv lock --check
      ▼
[7] CREATE GITHUB REPO     commit with provenance trailers · prove the commit
                           · create remote · push finalized initial repository
      ▼
[8] REMOTE ORG BOOTSTRAP   labels · repo settings · applicable seeding
      ▼
[9] REMOTE ATTESTATION     read the actual remote back · verify org profile
                           · verify the birth receipt · verify HEAD
      ▼
BIRTH: PASS
```

`uv lock` is stage 3. It is not something a product author is asked to
remember; it is a birth invariant, and a birth invariant belongs to the birth
engine.

So is the agent-facing metadata. `plugin-config.yaml` is chassis and every
generated Cursor rule is rendered from it, so a value in it that still describes
this template becomes an active, false instruction in the newborn — internally
consistent, and about a repository that does not exist. Stage 3 therefore
reconciles the config against the assembled tree **before** the rules are
rendered: `repo_name` and `domain` are derived from the newborn's own
`.l9/architecture.yaml`, an `app_entrypoint` is kept only if the module it names
is in the tree, and a capability is kept only while the evidence path declared
for it in `capability_evidence` exists. A rule template may declare its own
precondition with `<!-- L9_RENDER_REQUIRES: <config keys> -->`; an unqualified
rule is not rendered, and a previously rendered copy of it is removed.

Package-token substitution cannot do this. Renaming `l9_example_pkg.app:app` to
`<product>.app:app` produces a claim about a module an authoritative payload
never shipped, and `repo_name` / `domain` are literal template values no rename
ever touched. `make check-config` is the same computation as a gate, so a
repository that drifts later fails its own ladder rather than the next birth.

**Nothing is created until stage 6 is green.** A failed test does not leave a
half-born repository on GitHub — it leaves a work directory and a receipt.

Stage 5 is where **order is the contract**. Provenance is generated output, so it
is stamped *after* the product payload has been overlaid and *after* the
organization has had its say — never copied in with the template and hoped over.

## Parameters

| Variable | Required | Meaning |
|----------|----------|---------|
| `REPO` | yes | GitHub repository name |
| `PKG` | yes | snake_case Python package name |
| `DESC` | yes | one-line description |
| `PAYLOAD` | no | product files. A fragment is overlaid (payload wins on collision); a whole repository is **authoritative** — see below |
| `PAYLOAD_CONTRACT` | for an authoritative payload | the compiled `l9.birth-payload/v1` authorizing those bytes |
| `ORG` | no | GitHub owner (default `Quantum-L9`) |
| `WORK_DIR` | no | where the repository is assembled (default `/tmp/l9-births`) |
| `CLASS` | no | org repo class (default `non_constellation_python`) |
| `ORG_PROFILE_SRC` | no | local `Quantum-L9/.github` checkout — skips the `gh` read, enables an offline birth |
| `RECEIPT` | no | where to write the run's operator receipt JSON |
| `PRIVATE` | no | create the repository private |
| `NO_REMOTE` | no | stop after stage 5 — assemble, finalize, and validate only |

## What a PAYLOAD owns

`PAYLOAD` has two modes, and which one applies is decided by the payload's
shape, never by a flag.

| Payload | Mode | Contract | Absence means |
|---------|------|----------|---------------|
| a fragment — some files, part of a tree | **additive overlay** | not required | nothing. The template keeps everything the payload does not mention. |
| a standalone repository | **authoritative** | **required** | the product does not own that surface. It is removed. |

A payload is repository-shaped when it carries every path in
`repository_shape` — today `pyproject.toml`, `.l9/architecture.yaml`, `src/`,
`tests/`, and `scripts/inventory_check.py`. Identification is positive: a large
payload, or one that merely happens to have a `src/` directory, stays additive.

Shape is what the compiler reads to PROPOSE a classification. It is not what
birth acts on: stage 1 re-derives the classification from the same ownership
contract, so a hand-edited `"mode": "authoritative"` cannot promote a fragment
into a payload that deletes surfaces it never owned. A repository-shaped
directory with **no** compiled contract stops the birth — a decision that
removes product surfaces is not one to infer from a directory listing while
files are already being copied.

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

## The compiled payload

The birthing agent does not author the payload. It invokes a deterministic
compiler owned by this template, against an immutable snapshot of the actual
source repository.

```
ACTUAL SOURCE REPOSITORY          clean checkout @ immutable commit
        │
        ▼
Birth Agent                       orchestration only
        │
        ▼
BirthPayloadCompiler              reads actual files · computes hashes
(this template)                   classifies repository shape · rejects
        │                         engine-owned paths
        ▼
CompiledBirthPayload              l9.birth-payload/v1
        │
        ├──────────────┐
        ▼              ▼
source tree       payload-ownership.yaml
still supplies    template-owned policy
actual bytes      product/chassis split
        └──────┬───────┘
               ▼
        Birth stages 1-9
```

That dependency direction is the point. The compiler belongs to this template
because this template owns HOW A REPO IS BORN; the source repository owns its
product files; the agent owns neither.

### The contract

| Surface | Path |
|---------|------|
| schema | `scripts/birth-runner/schemas/birth-payload.schema.json` |
| compiler | `scripts/birth-runner/compile_birth_payload.py` |
| verifier | `scripts/birth-runner/verify_birth_payload.py` |
| ownership reader | `scripts/birth-runner/payload_ownership.py` |

The schema lives with the birth engine rather than under `.l9/` because it is
part of the engine's implementation contract — not something every newborn
should inherit a copy of.

```json
{
  "schema": "l9.birth-payload/v1",
  "source": {
    "repository": "Quantum-L9/IdeaOS",
    "revision": "<40-char sha>",
    "tree_sha": "<git tree sha>"
  },
  "mode": "authoritative",
  "repository_shape": { "matched": ["pyproject.toml", ".l9/architecture.yaml", "src", "tests", "scripts/inventory_check.py"] },
  "packages": { "python": ["ideaos"] },
  "files": [
    { "path": "pyproject.toml", "sha256": "<sha256>" },
    { "path": "src/ideaos/__init__.py", "sha256": "<sha256>" }
  ],
  "manifest_sha256": "<canonical manifest digest>"
}
```

**It is a manifest, not a second repository.** File contents stay in the source
tree and birth copies them from there; the contract only proves which bytes it
authorized.

**It carries evidence, not intent.** Deliberately absent: capabilities, desired
CI, repo class, template version, organization policy, the target repository's
name, a birth timestamp, absence declarations, per-file ownership, generated
files, future conformance state. Every one of those belongs to another authority
or is derivable from the files this manifest names, and duplicating it here
would create two truths for one question.

Absence needs no declaration either. Under an authoritative payload,
`payload-ownership.yaml` already makes a `product` surface the source does not
supply mean *this product does not have one* — so a `"Dockerfile": absent` entry
would be a second way to say what the manifest says by omission.

The digest is `birth_provenance.manifest_digest`, the same algorithm as
`MANIFEST.sha256` and the birth receipt: `sha256` over `<sha256>  <path>` lines,
path-sorted. One algorithm, three callers, and a human with `sha256sum` can
reproduce it without trusting any of them.

### The invariant

```
CompiledBirthPayload.files  ==  actual source snapshot  ==  bytes copied into assembly
```

Not approximately, and not "the same paths" — the same hashes. Stage 1
recomputes the manifest against the source tree immediately before assembly and
compares every one. Compilation and consumption are time-of-check/time-of-use
bound: if one byte changed in between, the birth stops while a work directory is
still the only thing that exists.

Two proofs come out of one birth, and they are never merged:

| Digest | Answers |
|--------|---------|
| payload `manifest_sha256` | what exactly did the product **source** contribute? |
| receipt `manifest_sha256` | what exactly was the repository **born** containing? |

### Failure semantics

Fail closed, always before the GitHub repository is created:

- a dirty authoritative source tree, or one with untracked files;
- a source that is not a git checkout, or has no commits;
- the source SHA or tree SHA moving after compilation;
- any file's hash changing, any authorized path disappearing, any unauthorized
  path appearing;
- a malformed contract, or an unrecognized schema version;
- an engine-owned provenance path present in the source;
- `PKG` naming a package the payload does not ship;
- a payload claiming `authoritative` that the ownership contract does not derive;
- duplicate or case-colliding paths — one of the two would be lost on a
  case-insensitive filesystem, and not the one the digest names;
- a symlink escaping the source root;
- a special filesystem object (device, socket, fifo) among the tracked files.

There is **no fallback** from an invalid compiled authoritative payload to a
naked-directory overlay. Silently birthing the additive way from a contract that
failed to reproduce is exactly the unverified path the contract exists to close.

### Checking a payload on its own

```bash
make birth-payload-check PAYLOAD_CONTRACT=/tmp/product.payload.json \
                         SOURCE=/path/to/product PKG=product_pkg
```

Same checks stage 1 runs, as a standalone report — `--json` for a machine
reader.

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

## Two records, two questions

A repository has two different relationships with the template that made it, and
collapsing them into one file is why *"which template made this?"* and *"is this
repository up to date?"* kept answering each other's question.

| File | Lifetime | Answers |
|------|----------|---------|
| `.l9-template-version` | **immutable** | the template version this repository was BORN from |
| `.l9/org-birth-profile.yaml` | **immutable** | its class, and the exact pair of commits it was born from |
| `.l9/birth-receipt.json` | **immutable** | the whole birth record, plus a digest over it |
| `.l9/template-state.yaml` | **mutable** | what it is expected to conform to **today** |

```
BIRTH INTEGRITY      "Is this repository genuinely what it claims it was born from?"
CURRENT CONFORMANCE  "Has it drifted from today's required org/template state?"
```

Reconciliation moves `.l9/template-state.yaml` and nothing else, so the history
reads `born from template@496fa88 -> reconciled to template@812bc11 -> reconciled
to template@e784b31` while the birth record keeps saying `496fa88` forever.

### Protected birth paths

A product payload owns its product. It never owns the record of its own birth:

```python
BIRTH_OWNED_PATHS = {
    ".l9-template-version",
    ".l9/org-birth-profile.yaml",
    ".l9/birth-receipt.json",
}
```

Those, plus `.l9/template-state.yaml`, are rejected in stage 1 when a payload
supplies one — fail closed, not silently overwritten. The failure this removes is
specific: a payload copied out of an older repository carries that repository's
`.l9-template-version`, the overlay wins on collision, and the newborn is born
claiming a provenance that belongs to somebody else.

### The version must be the version at the pinned SHA

The record pins a template commit, so the version it records is read **from that
commit**, not from the template working tree the birth ran out of:

```bash
git -C <template> show "$TEMPLATE_SHA:.l9-template-version"
```

If that disagrees with the assembled repository, the birth stops. Without it a
repository is stamped `template_version: 2.1.0` beside a `template_sha` whose
tree says `2.0.0` — a claim nothing downstream can ever check, discovered only
when someone finally reads both.

## The birth receipt

Every run writes an operator report to `<WORK_DIR>/<REPO>-birth-receipt.json`:
the two provenance SHAs, the resolved class, and per-stage results.

The repository's own permanent record is committed as `.l9/birth-receipt.json`:

```json
{
  "schema": "l9.birth-receipt/v1",
  "repository": "Quantum-L9/l9-observability-core",
  "repo_class": "non_constellation_python",
  "template": { "repository": "Quantum-L9/l9-repo-template",
                "sha": "496fa88ef517...", "version": "2.1.0" },
  "org_policy": { "repository": "Quantum-L9/.github", "sha": "01b8531f122..." },
  "payload_mode": "authoritative",
  "manifest_sha256": "...",
  "born_at": "2026-08-26T...",
  "digest": "sha256 over the above, canonical JSON, sorted keys"
}
```

and the root commit carries the same record in its trailers:

```
chore: birth Quantum-L9/l9-observability-core from l9-repo-template@496fa88ef517

L9-Birth-Receipt: sha256:ece28ca3bc69...
L9-Template: 496fa88ef517eb73d096c02f81dde088a0442b59
L9-Template-Version: 2.1.0
L9-Policy: 01b8531f122fee6b39876a6752e3fe4ce6a61674
L9-Class: non_constellation_python
```

Three independently comparable things come out of one birth:

```
root commit  ──────────  birth receipt  ──────────  repository contents
   trailers                  digest                    manifest_sha256
```

Mismatch anywhere = invalid birth.

## Proving it, later

Every repository born from this template carries the checker:

```bash
make birth-check                                    # in the verify ladder
python3 scripts/birth-runner/verify_birth_integrity.py --json
```

It reads the **root commit**, never `HEAD`, which is why its answer survives
years of ordinary development on top:

| Check | Proves |
|-------|--------|
| `receipt digest` | the receipt still hashes to the digest it claims |
| `template version` | `.l9-template-version` is the version the receipt records |
| `birth marker` | the `birth:` block agrees with the receipt |
| `conformance state` | a legible `.l9/template-state.yaml` exists (says nothing about drift) |
| `root commit` | exactly one root — no grafted unrelated history |
| `commit trailers` | the root commit carries the receipt's digest, SHAs, and class |
| `birth record intact` | the three birth-owned files are byte-identical to the root commit |
| `contents digest` | `manifest_sha256` covers what the root commit actually contains |

A repository with no `.l9/birth-receipt.json` reports **UNBORN** and passes:
this template was not born from itself, and repositories that predate the receipt
have nothing to attest. `--require-receipt` turns that into a failure, which is
what stage 6 uses on a newborn it has just stamped.

## What this repository does NOT own

Birth integrity is a **P0** — provenance corruption, unreconcilable, because
there is nothing trustworthy left to reconcile toward. Current conformance is
everything below it:

| Severity | Drift |
|----------|-------|
| **P0** | provenance corruption — receipt, trailers, or contents disagree |
| **P1** | security / policy — branch protection removed, required workflow bypassed, CODEOWNERS absent |
| **P2** | platform — CI reusable workflow behind the required revision, stale chassis files |
| **P3** | informational — a newer template version exists |

P1–P3 are answered by a **central drift engine** that enumerates managed
repositories, reads each `.l9/org-birth-profile.yaml` for its class, resolves the
desired state for that class, and opens reconciliation pull requests. That engine
does not live here, and neither does the per-class desired-state contract it
compares against: `Quantum-L9/.github` owns what the organization requires, and a
scheduled workflow copied into every repository is the duplication the whole
ownership split exists to prevent. What this template owns is the marker that
makes a repository discoverable, the class it declares, and the P0 proof above —
which the drift engine calls rather than reimplements.

Reconciliation is `detect -> classify -> propose patch -> open PR -> CI -> approve
-> merge -> re-attest`, never `detect drift -> push to main`.

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
