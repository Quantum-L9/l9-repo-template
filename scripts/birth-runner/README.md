# Repository birth runner

## Public operator / agent front door

Use `make birth` for production remote birth. It dispatches the canonical
`repo-birth-dispatch.yml` workflow and therefore crosses the PREPARE -> PUBLISH
fresh-runner privilege boundary introduced by PR A. The caller never mints the
publication token and never runs privileged publication locally.

```bash
make birth \
  REPO=idea-runtime \
  PKG=idea_runtime \
  DESC="Idea runtime" \
  VISIBILITY=private
```

For an authoritative product payload already committed in Quantum-L9:

```bash
make birth \
  REPO=idea-runtime \
  PKG=idea_runtime \
  DESC="Idea runtime" \
  PAYLOAD_REPO=Quantum-L9/idea-runtime-source \
  PAYLOAD_REF=<immutable-or-approved-ref> \
  PAYLOAD_CONTRACT_PATH=path/to/birth.payload.json
```

Optional dispatch inputs are exposed as Make variables:

| Make variable | Workflow input |
|---|---|
| `VISIBILITY` | `visibility` (`private` by default) |
| `CLASS` | `repo_class` |
| `CI_UNVERIFIED_REASON` | `ci_unverified_reason` |
| `GOVERNANCE_REF` | `governance_ref` |
| `PAYLOAD_REPO` | `payload_repo` |
| `PAYLOAD_REF` | `payload_ref` |
| `PAYLOAD_SUBPATH` | `payload_subpath` |
| `PAYLOAD_CONTRACT_PATH` | `payload_contract_path` |
| `FACTORY_REF` | workflow ref (`main` by default; useful for stacked factory testing) |

`make birth` returning successfully means GitHub accepted the birth request. It
does not mean the repository has already reached the lifecycle state `BORN`.
Query live truth separately:

```bash
make birth-status REPO=Quantum-L9/idea-runtime
make birth-status REPO=Quantum-L9/idea-runtime JSON=1
```

`birth-status` is read-only. It never updates `.l9/birth-receipt.json`.

## Lifecycle truth

The birth receipt is immutable historical provenance. Lifecycle status is live,
derived truth.

```text
birth receipt   = what happened at creation
org ruleset     = whether canonical CI currently governs the repository
Core CI run     = whether canonical CI actually evaluated the repository
birth-status    = current derived lifecycle state
```

States:

| State | Meaning |
|---|---|
| `LOCAL` | assembled and locally validated, not published |
| `PROVISIONAL` | published and enrolled, but no accepted canonical lifecycle success is yet observable |
| `BORN` | canonical required-workflow CI produced an accepted success |
| `QUARANTINED` | enrollment is absent or an accepted canonical lifecycle run failed before any success was earned |

The currently proven GitHub path is a required-workflow `pull_request` run after
birth. `l9-ci-core` also declares a default-branch native `push` lane. The status
reader is ready to accept a genesis push only when GitHub actually emits that
required-workflow run and its head commit is provably zero-parent. A normal later
default-branch push never counts as genesis evidence.

The repository does **not** own a Core caller workflow. Enrollment comes from the
active organization required-workflow ruleset pointing at:

```text
Quantum-L9/l9-ci-core/.github/workflows/org-ci.yml@refs/heads/main
```

A newborn with no `.github/workflows` directory can therefore be exactly correct.

## `make new-repo` is a lower-level compatibility surface

`make new-repo` remains useful for local/debug work and compatibility tests:

```bash
make birth-payload SOURCE=/path/to/source OUT=/tmp/source.payload.json

make new-repo \
  REPO=example \
  PKG=example \
  DESC="Example" \
  PAYLOAD=/path/to/source \
  PAYLOAD_CONTRACT=/tmp/source.payload.json
```

`new_repo.py` owns the canonical birth state machine. PR A splits production
execution across PREPARE/seal and PUBLISH so product-controlled code cannot run
with repository-creation authority. The direct `all()` path remains a guarded
compatibility topology, not the mobile production front door.

An authoritative payload is compiled, never inferred.
[`compile_birth_payload.py`](compile_birth_payload.py) reads a clean git snapshot
of the source repository and emits an `l9.birth-payload/v1` manifest. Stage 1
recomputes that manifest against the source tree and stops on disagreement via
[`verify_birth_payload.py`](verify_birth_payload.py).

| File | Role |
|---|---|
| [`birth_frontdoor.py`](birth_frontdoor.py) | public remote dispatch client |
| [`birth_status.py`](birth_status.py) | read-only lifecycle reconciler |
| [`new_repo.py`](new_repo.py) | canonical birth engine |
| [`canonical_ci.py`](canonical_ci.py) | CI enrollment and run-correlation law |
| [`compile_birth_payload.py`](compile_birth_payload.py) | payload compiler |
| [`verify_birth_payload.py`](verify_birth_payload.py) | payload reproducer |
| [`schemas/birth-payload.schema.json`](schemas/birth-payload.schema.json) | `l9.birth-payload/v1` contract |
| [`payload_ownership.py`](payload_ownership.py) | payload ownership reader |

Useful direct/debug flags on `new_repo.py`:

| Flag | Effect |
|---|---|
| `--no-remote` | assemble, finalize and validate without publication |
| `--org-profile-src <dir>` | read the class contract from a local `.github` checkout |
| `--receipt <path>` | write the external birth execution receipt to a chosen path |

## Staged scripts are debugging surfaces only

The numbered scripts below predate the canonical birth engine and remain for
one-stage debugging. They do not apply the full org birth profile and do not
attest the remote. They are not a production birth.

```bash
export PLAY_DIR=/tmp/museum-birth-demo
mkdir -p "$PLAY_DIR"
cp config.template.yaml "$PLAY_DIR/config.yaml"
# edit config
bash 01_preflight.sh
bash 02_bootstrap.sh
bash 03_verify.sh
# optional debug push only:
PUSH=1 bash 04_push.sh
```

Defaults: `OPEN_PR=0`, push off unless `PUSH=1`.
