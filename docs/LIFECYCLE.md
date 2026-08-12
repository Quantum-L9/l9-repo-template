# Lifecycle — generic Quantum-L9 Python repo

## Birth

1. GitHub **Use this template** (or `scripts/birth-runner/`).
2. `make rename PKG=your_pkg`
3. `make verify`
4. Optional: `make run` / `make obs-up`

Details: [ops/REPO_BIRTH.md](ops/REPO_BIRTH.md).

## Day-to-day

- Edit `src/` and helpers; keep hygiene (no eval/exec/print).
- Re-render Cursor rules after `plugin-config.yaml` edits: `make render-rules`.
- Refresh CI after pin bumps: `make sync-ci`.

## When to leave this template

- Building a Constellation **node** → [L9-Node-Template](https://github.com/Quantum-L9/L9-Node-Template)
- Birthing a `constellation_*` **dependency** → [Constellation.PackageTemplate](https://github.com/Quantum-L9/Constellation.PackageTemplate)

Do not gradually grow this museum into either sibling product.
