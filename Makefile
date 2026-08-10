PYTHON ?= python3

.DEFAULT_GOAL := help

.PHONY: help setup install-dev lint typecheck test inventory-check check-rules render-rules verify sync-ci rename ci

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Sync locked deps + install pre-commit hooks
	@command -v uv >/dev/null 2>&1 && uv sync --extra dev || $(PYTHON) -m pip install -e ".[dev]"
	@command -v pre-commit >/dev/null 2>&1 && pre-commit install || true

install-dev: ## Install editable package with dev extras
	@command -v uv >/dev/null 2>&1 && uv sync --extra dev || $(PYTHON) -m pip install -e ".[dev]"

lint: ## Ruff check + format check
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck: ## mypy on src/
	$(PYTHON) -m mypy src

test: ## pytest
	$(PYTHON) -m pytest -q

inventory-check: ## Fail closed on deny dirs / missing required files
	$(PYTHON) scripts/inventory_check.py

render-rules: ## Render .cursor/rules/*.mdc from templates + plugin-config.yaml
	$(PYTHON) scripts/render_cursor_rules.py

check-rules: ## Fail if rendered Cursor rules drift
	$(PYTHON) scripts/render_cursor_rules.py --check

verify: inventory-check check-rules lint typecheck test ## Full local validation ladder

ci: verify ## Alias for verify

sync-ci: ## Refresh .github + org files from pinned Quantum-L9/.github
	$(PYTHON) scripts/sync_ci_from_pack.py

# usage: make rename PKG=foo_bar
rename: ## Rewrite l9_example_pkg identity; reinstall; re-render rules
	@test -n "$(PKG)" || (echo "usage: make rename PKG=foo_bar" >&2; exit 2)
	$(PYTHON) scripts/bootstrap_rename.py --pkg $(PKG)
	@command -v uv >/dev/null 2>&1 && uv sync --extra dev || $(PYTHON) -m pip install -e ".[dev]"
	$(PYTHON) scripts/render_cursor_rules.py --force
