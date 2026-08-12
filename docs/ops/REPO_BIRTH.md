# Repo birth (non-Constellation)

## Manual (recommended)

1. Use template: `Quantum-L9/l9-repo-template`
2. Clone the new repo
3. `make rename PKG=your_pkg`
4. `make verify`
5. Push your feature branch; open PR via Cursor-Governance (`make gov-pr`) when wired

In-repo gates never open PRs (`OPEN_PR=0`).

## Automated runner

```bash
export PLAY_DIR=/tmp/museum-birth-demo
mkdir -p "$PLAY_DIR"
cp scripts/birth-runner/config.template.yaml "$PLAY_DIR/config.yaml"
# edit config.yaml: org, repo_name, package_name, description, work_dir
export PLAY_DIR
bash scripts/birth-runner/01_preflight.sh
bash scripts/birth-runner/02_bootstrap.sh
bash scripts/birth-runner/03_verify.sh
# optional remote (explicit):
PUSH=1 bash scripts/birth-runner/04_push.sh
```

No PackageTemplate plays catalog. No Gate-worker birth framing.
