# Parametric Cursor Rule Rendering

Reusable `.mdc.template` files become concrete `.cursor/rules/*.mdc` files using
per-repo values from `plugin-config.yaml`.

Adapted from the earlier L9 service-template body; museum defaults exclude FastAPI.

## First render

```bash
uv sync --extra dev
make render-rules
make check-rules
```

Use `--force` only when migrating existing hand-authored `.mdc` files:

```bash
python scripts/render_cursor_rules.py --force
```

## Ongoing workflow

```bash
make render-rules   # apply template/config changes
make check-rules    # fail if rendered rules drift
```

## Template syntax

Templates use Python `string.Template` placeholders (`${repo_name}`, list
variants `${protected_paths_bullets}`, etc.).

## Drift detection

`make check-rules` re-renders in memory and compares against committed
`.cursor/rules/*.mdc` files. Drift exits non-zero.
