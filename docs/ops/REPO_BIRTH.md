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
[3] FINALIZE               canonical LICENSE · uv lock · reconcile plugin-config
   AUTOMATICALLY           · render generated rules · regenerate manifests
      ▼
[4] APPLY ORG BIRTH        current Quantum-L9/.github · only applicable
    PROFILE                non-inheritable controls · current org SHA recorded
      ▼
[5] STAMP BIRTH            .l9-template-version · .l9/org-birth-profile.yaml
    PROVENANCE             · .l9/birth-receipt.json · .l9/template-state.yaml
      ▼
[6] VALIDATE BEFORE        inventory · hygiene · birth integrity · ci binding
    CREATION               · rules · lint · format · typecheck · tests · lock
      ▼
[7] PUBLISH ROOT COMMIT    commit with provenance trailers · prove the commit
                           · create remote · push finalized initial repository
                           → repository becomes PROVISIONAL
      ▼
[8] REMOTE ORG BOOTSTRAP   labels · repo settings · applicable seeding
      ▼
[9] CANONICAL CI           await l9-ci-core's verdict on the exact root SHA
                           · bounded timeout · never an unrelated run
      ▼
[10] REMOTE ATTESTATION    read the actual remote back · verify org profile
                           · verify the birth receipt · verify HEAD · verify CI
      ▼
BIRTH: PASS
STATE: BORN
```

## Creation is not birth

A repository that exists is not a repository that is born. Creating the remote,
pushing the root commit and applying organization settings prove that GitHub
accepted some bytes; none of it proves the code was ever evaluated.
`Quantum-L9/l9-observability-core` is the case that made this concrete — created,
pushed, attested, reported successful, with zero workflows and no canonical CI
run of any kind.

Birth therefore has four states, and the receipt names the one that happened:

| State | Meaning |
|---|---|
| `LOCAL` | assembled and locally validated; nothing published (`--no-remote`) |
| `PROVISIONAL` | root commit published; canonical CI not yet proven |
| `BORN` | canonical CI evaluated **this** root commit and succeeded |
| `QUARANTINED` | published, and canonical CI is missing, failed, or timed out |

Only `BORN` prints `BORN`. Publication and successful birth are separate
lifecycle events, which is also what keeps the model acyclic: CI cannot evaluate
a commit that does not exist, so birth waits **after** publishing rather than
gating the commit on CI.

A `QUARANTINED` repository is **preserved**, never auto-deleted. It is the
evidence.

## Invariants

| ID | Invariant |
|---|---|
| `BIRTH-CI-001` | Every governed newborn has an effective binding to the canonical CI authority. |
| `BIRTH-CI-002` | The newborn root commit is evaluated by canonical CI before birth is declared successful. |
| `BIRTH-CI-003` | Canonical CI concludes `success` for the newborn root SHA. |
| `BIRTH-CI-004` | Product payload materialization cannot silently disable or replace the binding. |
| `BIRTH-CI-005` | Birth completion relies on remotely observed CI state, never on local assumption. |

Enforced by `scripts/birth-runner/canonical_ci.py`; covered by
`tests/unit/test_canonical_ci.py` and `tests/integration/test_new_repo_local_birth.py`.

## The CI ownership boundary

    l9-ci-core        owns CI implementation and execution semantics
    the newborn       owns only the minimal binding that invokes it
    l9-repo-template  owns birth orchestration and this verification

Nothing in birth copies, reimplements, or second-guesses CI. `canonical_ci.py`
answers three questions about somebody else's CI: is this repository bound to
it, did it run for **this** commit, and did it succeed.

The accepted run must correlate to the root SHA. "Some run passed recently" is
not evidence — a stale success, a run on another branch, a run for another
commit and a run that reports no SHA at all are all rejected. Binding discovery
parses each workflow and reads `jobs.*.uses`; a `uses:` in a comment is not
enrollment.

A binding that points at a **Quantum-L9 CI workflow which is not the canonical
entrypoint** fails closed rather than being ignored. That is worse than no
binding: it looks like enrollment and evaluates something else.

## Current limitation — read this before running a real birth

There is no sanctioned mechanism that installs the binding yet.
`l9-ci-core/.l9/org-runtime-contract.yaml` sets `consumer_copy_required: false`
and `consumer_core_pin_allowed: false`, and expects a GitHub **organization
required-workflow ruleset** to reach the repository instead. Birth cannot
observe a ruleset from the client side, and the ruleset's live status is
unverified upstream: `organization-ruleset-live-enforcement` is recorded as
`status: UNKNOWN, evidence: []`.

So by default `make new-repo` now **stops at local validation** with a precise
diagnostic rather than producing another repository nothing evaluates. That is
deliberate: the gap is made loud instead of silent.

To publish anyway — knowing enrollment is unproven:

```bash
L9_BIRTH_CI_UNVERIFIED='ruleset enrollment applied out of band, ticket L9-1234' \
  make new-repo REPO=... PKG=... DESC=...
```

The reason is mandatory; a blank value is not an authorization. The breakglass
downgrades the missing-binding refusal to a recorded `WARN` and the repository
is left `PROVISIONAL` — it is never reported `BORN`. It does **not** excuse a
*wrong* binding, which still fails closed.

## Failure semantics

| Situation | Result |
|---|---|
| No binding, no breakglass | `BIRTH: FAIL` at local validation — nothing is created |
| Binding names a non-canonical authority | `BIRTH: FAIL` at local validation — nothing is created |
| CI never starts for the root SHA | `QUARANTINED` — "not enrolled, or the authority never triggered" |
| CI starts and does not conclude in `--ci-timeout` | `QUARANTINED` — "binding is live, the run is slow or stuck" |
| CI concludes anything other than `success` | `QUARANTINED`, with the run id and URL |
| Actions API unreadable past its retry budget | `QUARANTINED` — undeterminable is not success |

The two timeout diagnoses are deliberately distinct: "never started" and
"started but stuck" have different causes and different fixes.

`--ci-timeout` (default 900s) bounds the wait. Birth never polls forever.

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
| `ORG` | no | GitHub owner (default `Quantum-L9`) |
| `WORK_DIR` | no | where the repository is assembled (default `/tmp/l9-births`) |
| `CLASS` | no | org repo class (default `non_constellation_python`) |
| `ORG_PROFILE_SRC` | no | local `Quantum-L9/.github` checkout — skips the `gh` read, enables an offline birth |
| `RECEIPT` | no | where to write the run's operator receipt JSON |
| `PRIVATE` | no | create the repository private |
| `NO_REMOTE` | no | stop after stage 5 — assemble, finalize, and validate only (final state `LOCAL`) |

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
