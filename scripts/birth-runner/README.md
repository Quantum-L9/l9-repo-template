# Museum birth-runner

Generic **Use-template → rename → verify** (+ optional push) for non-Constellation
Quantum-L9 Python repos. Adapted from PackageTemplate dep-build-runner mechanics
without plays, constellation_* framing, or auto-merge.

## Config fields

```yaml
org: "Quantum-L9"
repo_name: "my-side-project"
package_name: "my_side_project"
description: "One-line description"
work_dir: "/tmp/l9-museum-births"
template_repo: "Quantum-L9/l9-repo-template"  # optional
template_src: ""  # optional local path; skips clone when set
```

## Run

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
