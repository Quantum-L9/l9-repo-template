#!/usr/bin/env bash
set -euo pipefail
PLAY_DIR="${PLAY_DIR:-$(pwd)}"
CHECKPOINT="$PLAY_DIR/.checkpoints/02_bootstrap.done"
[[ -f "$CHECKPOINT" ]] && echo "02 already done." && exit 0

echo "=== 02_bootstrap (museum birth) ==="
eval "$(PLAY_DIR="$PLAY_DIR" python3 - <<'PYEOF'
import os, yaml
cfg = yaml.safe_load(open(os.environ["PLAY_DIR"] + "/config.yaml", encoding="utf-8"))
print(f"ORG={cfg['org']}")
print(f"REPO_NAME={cfg['repo_name']}")
print(f"PACKAGE_NAME={cfg['package_name']}")
print(f"WORK_DIR={cfg['work_dir']}")
print(f"TEMPLATE_REPO={cfg.get('template_repo') or 'Quantum-L9/l9-repo-template'}")
print(f"TEMPLATE_SRC={cfg.get('template_src') or ''}")
PYEOF
)"

DEST="${WORK_DIR}/${REPO_NAME}"
mkdir -p "$WORK_DIR"

if [[ -d "$DEST/.git" ]]; then
  echo "Scaffold already exists at $DEST, skipping clone/copy."
else
  if [[ -n "$TEMPLATE_SRC" ]]; then
    echo "Copying local template from $TEMPLATE_SRC"
    # Prefer rsync if available; else cp -R
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --exclude .git --exclude .venv --exclude __pycache__ \
        "$TEMPLATE_SRC/" "$DEST/"
    else
      mkdir -p "$DEST"
      cp -R "$TEMPLATE_SRC/." "$DEST/"
      rm -rf "$DEST/.git" "$DEST/.venv"
    fi
    cd "$DEST"
    git init -b main
    git remote add origin "https://github.com/${ORG}/${REPO_NAME}.git" || true
  else
    gh repo clone "${TEMPLATE_REPO}" "${DEST}"
    cd "${DEST}"
    rm -rf .git
    git init -b main
    git remote add origin "https://github.com/${ORG}/${REPO_NAME}.git"
  fi

  # Rename example package identity
  if [[ -f Makefile ]]; then
    make rename PKG="${PACKAGE_NAME}"
  else
    python3 scripts/bootstrap_rename.py --pkg "${PACKAGE_NAME}"
  fi
fi

touch "$PLAY_DIR/.checkpoints/02_bootstrap.done"
echo "02_bootstrap PASSED — scaffold at ${DEST}"
