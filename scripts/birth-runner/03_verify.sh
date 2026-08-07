#!/usr/bin/env bash
set -euo pipefail
PLAY_DIR="${PLAY_DIR:-$(pwd)}"
CHECKPOINT="$PLAY_DIR/.checkpoints/03_verify.done"
[[ -f "$CHECKPOINT" ]] && echo "03 already done." && exit 0

echo "=== 03_verify (museum birth) ==="
eval "$(PLAY_DIR="$PLAY_DIR" python3 - <<'PYEOF'
import os, yaml
cfg = yaml.safe_load(open(os.environ["PLAY_DIR"] + "/config.yaml", encoding="utf-8"))
print(f"REPO_NAME={cfg['repo_name']}")
print(f"WORK_DIR={cfg['work_dir']}")
PYEOF
)"

DEST="${WORK_DIR}/${REPO_NAME}"
cd "${DEST}"
OPEN_PR=0 make pr-check

touch "$PLAY_DIR/.checkpoints/03_verify.done"
echo "03_verify PASSED"
