# Museum birth-runner

## `make new-repo` — the birth primitive

```bash
make new-repo \
  REPO=l9-observability-core \
  PKG=l9_observability_core \
  DESC="Canonical backend-neutral observability domain contracts" \
  PAYLOAD=/path/to/l9-observability-core
```

`new_repo.py` is the orchestrator: an eight-stage state machine that preflights,
assembles, finalizes (`uv lock` included), applies the current
`Quantum-L9/.github` birth profile, validates the newborn **before** anything is
created, creates and pushes it, invokes the org bootstrap immediately instead of
waiting for the hourly sweep, and then reads the remote back to attest it.

Full contract: [`docs/ops/REPO_BIRTH.md`](../../docs/ops/REPO_BIRTH.md).

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
