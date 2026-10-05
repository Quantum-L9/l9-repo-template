# Parametric Cursor Rule Rendering

Reusable `.mdc.template` files become concrete `.cursor/rules/*.mdc` files using
per-repo values from `plugin-config.yaml`.

Chassis templates:

- `l9-python-repo.mdc.template` — generic repository/chassis invariants
- `fastapi.mdc.template` — optional FastAPI conventions for the reference payload
  (rendered only when `app_entrypoint` is materialized)
- `l9-agents.mdc.template` / `00-global` / `10-domain-cartridge` — agent cartridge

Generated rules describe repository and chassis invariants only. They do not
classify the product kind of the repository they are rendered into.

## First render

```bash
uv sync --extra dev
make render-rules --force
make check-rules
```

## Ongoing

```bash
make render-rules
make check-rules
```

Hand-edit templates only; generated `.mdc` files are managed.
