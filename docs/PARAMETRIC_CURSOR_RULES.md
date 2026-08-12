# Parametric Cursor Rule Rendering

Reusable `.mdc.template` files become concrete `.cursor/rules/*.mdc` files using
per-repo values from `plugin-config.yaml`.

Museum templates:

- `l9-python-repo.mdc.template` — non-Constellation Quantum-L9 Python invariants
- `fastapi.mdc.template` — optional FastAPI conventions (no Gate/SDK)
- `l9-agents.mdc.template` / `00-global` / `10-domain-cartridge` — agent cartridge

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
