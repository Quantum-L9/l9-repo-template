PYTHON ?= python3

.PHONY: install-dev lint typecheck test inventory-check verify sync-ci rename

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest -q

inventory-check:
	$(PYTHON) scripts/inventory_check.py

verify: inventory-check lint typecheck test

sync-ci:
	$(PYTHON) scripts/sync_ci_from_pack.py

# usage: make rename PKG=foo_bar
rename:
	@test -n "$(PKG)" || (echo "usage: make rename PKG=foo_bar" >&2; exit 2)
	$(PYTHON) scripts/bootstrap_rename.py --pkg $(PKG)
	@command -v uv >/dev/null 2>&1 && uv sync --extra dev || $(PYTHON) -m pip install -e ".[dev]"
