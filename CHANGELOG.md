# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Identity correction: museum is non-Constellation Quantum-L9 Python template (side-by-side with L9-Node-Template and Constellation.PackageTemplate)
- Default example is thin FastAPI hello + optional PackageTemplate-style helpers (no constellation-node-sdk / create_node_app / handlers / spec.yaml)

### Added

- `scripts/repo_hygiene_audit.py` + Semgrep museum hygiene rules
- `scripts/birth-runner/` generic Use-template → rename → verify (`OPEN_PR=0`)
- Parametric Cursor rules `l9-python-repo` + `fastapi` for generic repos
- Docs: WHEN_TO_USE, VALIDATION, LIFECYCLE, ops/REPO_BIRTH
- Tests reorganized under `tests/unit` + `tests/integration`

### Added

- Core thin Makefile facade + `Repo.mk` product targets + `gov-*` WS= wrappers
- Vendored `tools/l9_repo` repository-execution runtime (`L9_REPO_RUNTIME_PIN`)
- In-repo `make pr-check` (`OPEN_PR=0`) and `make agent-check` via Core runtime

- Gate-routed worker shell via constellation-node-sdk (`app.py` / `handlers.py` / `spec.yaml`)
- uv Dockerfile + thin docker-compose; `make run` / `dev` / `wait-http` / `preflight`
- Optional file-inv observability compose (`make obs-up`)
- `.semgrep/semgrep-rules.yaml` wired into l9-analysis
- docs/examples (CodeRabbit, SLO alerts) + secret-rotation checklist
- Parametric Cursor rules renderer (`make render-rules` / `check-rules`) from file-inv DX
- Thin `.vscode` / `.devcontainer` surfaces
- Thin L9 Python GitHub Template skeleton (`l9_example_pkg`)
- `make verify`, `make sync-ci`, and `make rename` force-multipliers
- CI surfaces seeded from `Quantum-L9/.github` via `make sync-ci`
