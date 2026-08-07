#!/usr/bin/env bash
set -euo pipefail
PLAY_DIR="${PLAY_DIR:-$(pwd)}"
CHECKPOINT="$PLAY_DIR/.checkpoints/01_preflight.done"
[[ -f "$CHECKPOINT" ]] && echo "01 already done." && exit 0

echo "=== 01_preflight (museum birth) ==="
fail() { echo "FAIL: $1" >&2; exit 1; }

command -v git >/dev/null 2>&1 || fail "git not found"
command -v python3 >/dev/null 2>&1 || fail "python3 not found"
command -v uv >/dev/null 2>&1 || fail "uv not found"
# gh only required when cloning from GitHub (no template_src)
python3 -c "import yaml" 2>/dev/null || python3 -m pip install pyyaml -q

CONFIG="$PLAY_DIR/config.yaml"
[[ -f "$CONFIG" ]] || fail "config.yaml not found in $PLAY_DIR"

PLAY_DIR="$PLAY_DIR" python3 - <<'PYEOF'
import os, sys, yaml
cfg = yaml.safe_load(open(os.environ["PLAY_DIR"] + "/config.yaml", encoding="utf-8"))
required = ["org", "repo_name", "package_name", "description", "work_dir"]
missing = [k for k in required if not cfg.get(k)]
if missing:
    print(f"config.yaml missing keys: {missing}", file=sys.stderr)
    sys.exit(1)
if "CHANGE_ME" in str(cfg["repo_name"]) or "CHANGE_ME" in str(cfg["description"]):
    print("config.yaml still has CHANGE_ME placeholder", file=sys.stderr)
    sys.exit(1)
pkg = cfg["package_name"]
if not pkg or "_" not in pkg and not pkg.isidentifier():
    # allow simple identifiers without underscore
    if not str(pkg).isidentifier():
        print("package_name must be a Python identifier", file=sys.stderr)
        sys.exit(1)
src = (cfg.get("template_src") or "").strip()
if not src:
    import shutil
    if shutil.which("gh") is None:
        print("gh CLI required when template_src is empty", file=sys.stderr)
        sys.exit(1)
print("config.yaml OK")
PYEOF

mkdir -p "$PLAY_DIR/.checkpoints"
touch "$CHECKPOINT"
echo "01_preflight PASSED"
