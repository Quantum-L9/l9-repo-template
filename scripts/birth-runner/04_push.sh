#!/usr/bin/env bash
set -euo pipefail
PLAY_DIR="${PLAY_DIR:-$(pwd)}"
CHECKPOINT="$PLAY_DIR/.checkpoints/04_push.done"
[[ -f "$CHECKPOINT" ]] && echo "04 already done." && exit 0

if [[ "${PUSH:-0}" != "1" ]]; then
  echo "04_push SKIPPED (set PUSH=1 to enable). OPEN_PR stays 0; no auto-merge."
  exit 0
fi

echo "=== 04_push (museum birth, optional) ==="
eval "$(PLAY_DIR="$PLAY_DIR" python3 - <<'PYEOF'
import os, yaml
cfg = yaml.safe_load(open(os.environ["PLAY_DIR"] + "/config.yaml", encoding="utf-8"))
print(f"REPO_NAME={cfg['repo_name']}")
print(f"WORK_DIR={cfg['work_dir']}")
print(f"ORG={cfg['org']}")
PYEOF
)"

DEST="${WORK_DIR}/${REPO_NAME}"
cd "${DEST}"
git add -A
git status
if git diff --cached --quiet; then
  echo "nothing to commit"
else
  git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -m "chore: birth from l9-repo-template"
fi
git push -u origin HEAD
echo "04_push PASSED (PR open is manual / gov-pr; OPEN_PR=0)"
touch "$CHECKPOINT"
