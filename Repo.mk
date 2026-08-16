# Product targets and CG WS= wrappers. Core facade targets stay in Makefile.
PKG_APP ?= l9_example_pkg.app:app
GOV_ROOT ?= $(HOME)/.cursor-governance
OPEN_PR ?= 0

# Prefer local venv for facade + product recipes (L9_REPO uses deferred PYTHON).
ifneq ($(wildcard $(CURDIR)/.venv/bin/python),)
PYTHON := $(CURDIR)/.venv/bin/python
endif
PYTHON ?= python3

.PHONY: help install-dev setup-hooks lint typecheck inventory-check hygiene-check \
	check-rules render-rules verify rename ci run dev wait-http \
	preflight obs-up obs-down obs-ps pr-check PR-check Pr-check test-cov \
	birth-preflight birth-bootstrap birth-verify \
	gov-pr-check gov-pr gov-start gov-wiring-check regenerate-manifest

# Override thin-facade help to list product + governance wrappers.
help:
	@echo "Core facade (tools.l9_repo):"
	@$(L9_REPO) help
	@echo ""
	@echo "Product / governance wrappers:"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' Repo.mk \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install-dev: ## Sync locked deps (uv) or pip editable+dev
	@command -v uv >/dev/null 2>&1 && uv sync --extra dev || $(PYTHON) -m pip install -e ".[dev]"

setup-hooks: ## Install pre-commit hooks when available
	@command -v pre-commit >/dev/null 2>&1 && pre-commit install || true

lint: ## Ruff check + format check
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck: ## mypy on src/
	$(PYTHON) -m mypy src

inventory-check: ## Fail closed on deny dirs / missing required files
	$(PYTHON) scripts/inventory_check.py

hygiene-check: ## Generic hygiene (eval/exec/print + scaffold bans)
	$(PYTHON) scripts/repo_hygiene_audit.py

render-rules: ## Render .cursor/rules/*.mdc from templates + plugin-config.yaml
	$(PYTHON) scripts/render_cursor_rules.py

check-rules: ## Fail if rendered Cursor rules drift
	$(PYTHON) scripts/render_cursor_rules.py --check

preflight: ## Validate .env.example (or ENV_FILE=...) museum keys
	$(PYTHON) scripts/preflight_local_env.py $${ENV_FILE:-.env.example}

test-cov: ## Pytest with coverage (no hard library threshold)
	$(PYTHON) -m pytest -q --cov=l9_example_pkg --cov-report=term-missing

verify: inventory-check hygiene-check check-rules lint typecheck ## Full local product validation ladder
	$(PYTHON) -m pytest -q

ci: verify ## Alias for verify

run: ## Run FastAPI hello with uvicorn (PKG_APP=package.app:app)
	$(PYTHON) -m uvicorn $(PKG_APP) --host $${HOST:-127.0.0.1} --port $${PORT:-8000}

dev: ## Build/run api via docker compose
	docker compose up --build

wait-http: ## Wait for URL (URL=http://127.0.0.1:8000/v1/health TIMEOUT=30)
	$(PYTHON) scripts/wait_for_http.py $${URL:-http://127.0.0.1:8000/v1/health} $${TIMEOUT:-30}

obs-up: ## Start optional local obs stack (Grafana/Prom/Tempo/OTelCol)
	docker compose -f observability/docker-compose.observability.yml up -d --wait

obs-down: ## Stop optional local obs stack
	docker compose -f observability/docker-compose.observability.yml down

obs-ps: ## Show optional local obs stack status
	docker compose -f observability/docker-compose.observability.yml ps

birth-preflight: ## Birth-runner preflight (PLAY_DIR=...)
	@test -n "$(PLAY_DIR)" || (echo "usage: make birth-preflight PLAY_DIR=/tmp/birth" >&2; exit 2)
	PLAY_DIR="$(PLAY_DIR)" bash scripts/birth-runner/01_preflight.sh

birth-bootstrap: ## Birth-runner bootstrap (PLAY_DIR=...)
	@test -n "$(PLAY_DIR)" || (echo "usage: make birth-bootstrap PLAY_DIR=/tmp/birth" >&2; exit 2)
	PLAY_DIR="$(PLAY_DIR)" bash scripts/birth-runner/02_bootstrap.sh

birth-verify: ## Birth-runner verify (PLAY_DIR=...)
	@test -n "$(PLAY_DIR)" || (echo "usage: make birth-verify PLAY_DIR=/tmp/birth" >&2; exit 2)
	PLAY_DIR="$(PLAY_DIR)" bash scripts/birth-runner/03_verify.sh

# usage: make rename PKG=foo_bar
rename: ## Rewrite l9_example_pkg identity; reinstall; re-render rules
	@test -n "$(PKG)" || (echo "usage: make rename PKG=foo_bar" >&2; exit 2)
	$(PYTHON) scripts/bootstrap_rename.py --pkg $(PKG)
	@command -v uv >/dev/null 2>&1 && uv sync --extra dev || $(PYTHON) -m pip install -e ".[dev]"
	$(PYTHON) scripts/render_cursor_rules.py --force

regenerate-manifest: ## Refresh MANIFEST.sha256 for runtime-critical paths
	$(PYTHON) scripts/regenerate_runtime_manifest.py

pr-check: verify ## In-repo product gate (OPEN_PR stays 0; use gov-pr to open)
	@command -v uv >/dev/null 2>&1 && uv lock --check || true
	@if [ "$(OPEN_PR)" != "0" ]; then \
		echo "OPEN_PR=$(OPEN_PR): in-repo pr-check never opens a PR; use make gov-pr" >&2; \
	fi

PR-check Pr-check: pr-check

# --- Cursor-Governance control plane (WS= callers; never vendor CG scripts) ---

gov-pr-check: ## CG pr-check against this workspace (WS=)
	@if [ ! -d "$(GOV_ROOT)" ]; then \
		echo "gov: skip — GOV_ROOT missing ($(GOV_ROOT)); wire Cursor-Governance then retry"; \
	else \
		$(MAKE) -C "$(GOV_ROOT)" pr-check WS="$(CURDIR)"; \
	fi

gov-pr: ## CG pr (open + remediate) against this workspace (WS=)
	@if [ ! -d "$(GOV_ROOT)" ]; then \
		echo "gov: skip — GOV_ROOT missing ($(GOV_ROOT)); wire Cursor-Governance then retry"; \
	else \
		$(MAKE) -C "$(GOV_ROOT)" pr WS="$(CURDIR)"; \
	fi

gov-start: ## CG start for this workspace (WS=)
	@if [ ! -d "$(GOV_ROOT)" ]; then \
		echo "gov: skip — GOV_ROOT missing ($(GOV_ROOT)); wire Cursor-Governance then retry"; \
	else \
		$(MAKE) -C "$(GOV_ROOT)" start WS="$(CURDIR)"; \
	fi

gov-wiring-check: ## CG wiring-check for this workspace (WS=)
	@if [ ! -d "$(GOV_ROOT)" ]; then \
		echo "gov: skip — GOV_ROOT missing ($(GOV_ROOT)); wire Cursor-Governance then retry"; \
	else \
		$(MAKE) -C "$(GOV_ROOT)" wiring-check WS="$(CURDIR)"; \
	fi
