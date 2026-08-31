# Museum birth-runner

## `make new-repo` — the birth primitive

```bash
make birth-payload SOURCE=/path/to/l9-observability-core OUT=/tmp/obs.payload.json

make new-repo \
  REPO=l9-observability-core \
  PKG=l9_observability_core \
  DESC="Canonical backend-neutral observability domain contracts" \
  PAYLOAD=/path/to/l9-observability-core \
  PAYLOAD_CONTRACT=/tmp/obs.payload.json
```

`new_repo.py` is the orchestrator: an eight-stage state machine that preflights,
assembles, finalizes (`uv lock` included), applies the current
`Quantum-L9/.github` birth profile, validates the newborn **before** anything is
created, creates and pushes it, invokes the org bootstrap immediately instead of
waiting for the hourly sweep, and then reads the remote back to attest it.

Full contract: [`docs/ops/REPO_BIRTH.md`](../../docs/ops/REPO_BIRTH.md).

`PAYLOAD` is additive when it is a fragment and **authoritative** when it is a
standalone repository — see
[`payload-ownership.yaml`](payload-ownership.yaml), which declares what a
product inherits from this template and what it does not. Absence is meaningless
in an overlay and meaningful in a repository: a product that ships no Dockerfile
is not handed the template's.

An authoritative payload is **compiled**, never inferred.
[`compile_birth_payload.py`](compile_birth_payload.py) reads a clean git snapshot
of the actual source repository and emits an `l9.birth-payload/v1` manifest —
which files, from which revision, at which hashes. Stage 1 recomputes that
manifest against the source tree and stops the birth on any disagreement
([`verify_birth_payload.py`](verify_birth_payload.py)). The contract carries
evidence only: the bytes stay in the source repository, and nothing about CI,
capabilities, or birth provenance appears in it.

| File | Role |
|------|------|
| [`compile_birth_payload.py`](compile_birth_payload.py) | compiler — snapshot to manifest |
| [`verify_birth_payload.py`](verify_birth_payload.py) | consumer-side reproduction of that manifest |
| [`schemas/birth-payload.schema.json`](schemas/birth-payload.schema.json) | published `l9.birth-payload/v1` contract |
| [`payload_ownership.py`](payload_ownership.py) | the one reader of `payload-ownership.yaml` |

Useful flags for local work:

| Flag | Effect |
|------|--------|
| `--no-remote` | stop after stage 5 — assemble, finalize, validate only |
| `--org-profile-src <dir>` | read the class contract from a local `.github` checkout (offline) |
| `--receipt <path>` | write the birth receipt JSON somewhere specific |

## Staged scripts (debugging surfaces)

The four numbered scripts below predate `make new-repo` and remain for
debugging one stage at a time. They do **not** apply the org birth profile and
do **not** attest the remote — they are not a birth.

### Config fields

```yaml
org: "Quantum-L9"
repo_name: "my-side-project"
package_name: "my_side_project"
description: "One-line description"
work_dir: "/tmp/l9-museum-births"
template_repo: "Quantum-L9/l9-repo-template"  # optional
template_src: ""  # optional local path; skips clone when set
```

### Run

```bash
export PLAY_DIR=/tmp/museum-birth-demo
mkdir -p "$PLAY_DIR"
cp config.template.yaml "$PLAY_DIR/config.yaml"
# edit config
bash 01_preflight.sh
bash 02_bootstrap.sh
bash 03_verify.sh
# optional:
PUSH=1 bash 04_push.sh
```

Defaults: `OPEN_PR=0`, push off unless `PUSH=1`.
