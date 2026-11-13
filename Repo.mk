# l9-repo-template repository-owned Make implementation (Repository Execution V2).
#
# The root Makefile is the Core-generated `make-v1` facade (l9.repo-execution/v2,
# declared in .l9/repo-workflow.json). It owns `help setup validate check test`
# and routes each phase to the `repo-<phase>` leaf below; regenerate it with
# Core's `python3 -m tools.l9_repo --workspace <repo> reconcile`, never by hand.
# This file must not redefine a facade verb. Everything else here — product,
# birth and governance wrappers — is repository-owned.
PKG_APP ?= l9_example_pkg.app:app
GOV_ROOT ?= $(HOME)/.cursor-governance
OPEN_PR ?= 0
FACTORY_REF ?= main
VISIBILITY ?= private
VENV ?= $(CURDIR)/.venv

# Prefer the repository venv once `make setup` has created it. Each facade phase
# is its own `make` invocation, so phases after setup resolve to the venv.
ifneq ($(wildcard $(VENV)/bin/python),)
PYTHON := $(VENV)/bin/python
endif
PYTHON ?= python3

.PHONY: repo-setup repo-validate repo-check repo-test agent-check clean \
	install-dev setup-hooks lint lint-fix typecheck inventory-check hygiene-check \
	check-rules render-rules check-config reconcile-config verify rename ci run dev wait-http \
	preflight obs-up obs-down obs-ps pr-check PR-check Pr-check test-cov \
	birth birth-status new-repo birth-payload birth-payload-check birth-check birth-preflight \
	birth-bootstrap birth-verify \
	gov-pr-check gov-pr gov-start gov-wiring-check

# ─── Repository Execution V2 leaves (reached through the generated facade) ───
# setup installs into a repository venv: the hosted runner's system interpreter
# is externally managed (PEP 668), and a venv keeps every later phase on the
# same locked dependency set.
repo-setup: ## Create .venv and install the project with its dev extras (uv sync when uv is present)
	@if command -v uv >/dev/null 2>&1; then \
		UV_PROJECT_ENVIRONMENT="$(VENV)" uv sync --locked --extra dev; \
	else \
		python3 -m venv "$(VENV)"; \
		"$(VENV)/bin/python" -m pip install --upgrade pip; \
		"$(VENV)/bin/python" -m pip install -e ".[dev]"; \
	fi

repo-validate: inventory-check hygiene-check ## Chassis inventory + hygiene validation (no mutation)

repo-check: lint typecheck ## Static checks: ruff check, ruff format --check, mypy src

repo-test: ## The repository test suite
	$(PYTHON) -m pytest -q

agent-check: ## Agent completion gate: validate + check + test, then prove the tree did not change
	@before="$$(git rev-parse HEAD) $$(git status --porcelain --untracked-files=all | sha256sum)"; \
	$(MAKE) --no-print-directory validate check test; \
	after="$$(git rev-parse HEAD) $$(git status --porcelain --untracked-files=all | sha256sum)"; \
	if [ "$$before" != "$$after" ]; then \
		echo "agent-check FAIL: HEAD or worktree changed during verification" >&2; \
		git status --porcelain --untracked-files=all >&2; \
		exit 1; \
	fi; \
	echo "agent-check: PASS"

clean: ## Remove tool caches (.pytest_cache .mypy_cache .ruff_cache)
	rm -rf -- "$(CURDIR)/.pytest_cache" "$(CURDIR)/.mypy_cache" "$(CURDIR)/.ruff_cache"

install-dev: ## Sync locked deps (uv) or pip editable+dev
	@if command -v uv >/dev/null 2>&1; then \
		uv sync --extra dev || (echo "uv sync failed — not falling back to pip" >&2; exit 1); \
	else \
		$(PYTHON) -m pip install -e ".[dev]"; \
	fi

setup-hooks: ## Install pre-commit hooks when available
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit install; \
	else \
		echo "pre-commit not installed — skipping hook install"; \
	fi

lint: ## Ruff check + format check
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

lint-fix: ## Ruff safe autofix + format (the writing half of `lint`)
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

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

check-config: ## Fail if plugin-config.yaml claims what this repository is not
	$(PYTHON) scripts/reconcile_plugin_config.py --check

reconcile-config: ## Rewrite plugin-config.yaml to describe this repository
	$(PYTHON) scripts/reconcile_plugin_config.py

preflight: ## Validate .env.example (or ENV_FILE=...) museum keys
	$(PYTHON) scripts/preflight_local_env.py $${ENV_FILE:-.env.example}

test-cov: ## Pytest with coverage (no hard library threshold)
	$(PYTHON) -m pytest -q --cov=l9_example_pkg --cov-report=term-missing

birth-check: ## Prove this repo is what its birth record claims (UNBORN repos pass)
	$(PYTHON) scripts/birth-runner/verify_birth_integrity.py --root .

verify: inventory-check hygiene-check birth-check check-config check-rules lint typecheck ## Full local product validation ladder
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

# ─── Repository birth ────────────────────────────────────────────────────────
# `birth` is the public remote operator/agent front door. It dispatches the
# canonical two-runner factory workflow; it does not run privileged birth in the
# caller's process. `birth-status` is a read-only lifecycle query. `new-repo`
# remains the direct/debug compatibility primitive and must not become the mobile
# production entrypoint.

birth: ## Dispatch secure factory birth (REPO= PKG= DESC= [VISIBILITY=private|public] [PAYLOAD_REPO= PAYLOAD_REF=])
	@test -n "$(REPO)" || (echo "usage: make birth REPO=<name> PKG=<pkg> DESC=<text> [PAYLOAD_REPO=Quantum-L9/repo PAYLOAD_REF=<ref>]" >&2; exit 2)
	@test -n "$(PKG)"  || (echo "usage: make birth REPO=<name> PKG=<pkg> DESC=<text> [PAYLOAD_REPO=Quantum-L9/repo PAYLOAD_REF=<ref>]" >&2; exit 2)
	@test -n "$(DESC)" || (echo "usage: make birth REPO=<name> PKG=<pkg> DESC=<text> [PAYLOAD_REPO=Quantum-L9/repo PAYLOAD_REF=<ref>]" >&2; exit 2)
	$(PYTHON) scripts/birth-runner/birth_frontdoor.py \
		--repo "$(REPO)" \
		--pkg "$(PKG)" \
		--desc "$(DESC)" \
		--visibility "$(VISIBILITY)" \
		--factory-ref "$(FACTORY_REF)" \
		$(if $(CLASS),--repo-class "$(CLASS)",) \
		$(if $(CI_UNVERIFIED_REASON),--ci-unverified-reason "$(CI_UNVERIFIED_REASON)",) \
		$(if $(GOVERNANCE_REF),--governance-ref "$(GOVERNANCE_REF)",) \
		$(if $(PAYLOAD_REPO),--payload-repo "$(PAYLOAD_REPO)",) \
		$(if $(PAYLOAD_REF),--payload-ref "$(PAYLOAD_REF)",) \
		$(if $(PAYLOAD_SUBPATH),--payload-subpath "$(PAYLOAD_SUBPATH)",) \
		$(if $(PAYLOAD_CONTRACT_PATH),--payload-contract-path "$(PAYLOAD_CONTRACT_PATH)",) \
		$(if $(PRODUCT_BIRTH_BINDING_PATH),--product-birth-binding-path "$(PRODUCT_BIRTH_BINDING_PATH)",) \
		$(if $(PRODUCT_MANIFEST_PATH),--product-manifest-path "$(PRODUCT_MANIFEST_PATH)",)

birth-status: ## Derive live lifecycle truth (REPO=<name|owner/name> [JSON=1])
	@test -n "$(REPO)" || (echo "usage: make birth-status REPO=<name|owner/name> [JSON=1]" >&2; exit 2)
	$(PYTHON) scripts/birth-runner/birth_status.py \
		--repo "$(REPO)" \
		$(if $(JSON),--json,)

# The targets below stay as lower-level/debugging surfaces.
birth-payload: ## Compile a birth payload (SOURCE=<clean checkout> OUT=<payload.json> [MODE=])
	@test -n "$(SOURCE)" || (echo "usage: make birth-payload SOURCE=<checkout> OUT=<payload.json>" >&2; exit 2)
	@test -n "$(OUT)"    || (echo "usage: make birth-payload SOURCE=<checkout> OUT=<payload.json>" >&2; exit 2)
	$(PYTHON) scripts/birth-runner/compile_birth_payload.py \
		--source "$(SOURCE)" \
		--out "$(OUT)" \
		$(if $(SOURCE_REPO),--source-repository "$(SOURCE_REPO)",) \
		$(if $(MODE),--require-mode "$(MODE)",)

birth-payload-check: ## Reproduce a compiled payload against its source (PAYLOAD_CONTRACT= SOURCE= [PKG=])
	@test -n "$(PAYLOAD_CONTRACT)" || (echo "usage: make birth-payload-check PAYLOAD_CONTRACT=<payload.json> SOURCE=<checkout>" >&2; exit 2)
	@test -n "$(SOURCE)"           || (echo "usage: make birth-payload-check PAYLOAD_CONTRACT=<payload.json> SOURCE=<checkout>" >&2; exit 2)
	$(PYTHON) scripts/birth-runner/verify_birth_payload.py \
		--payload "$(PAYLOAD_CONTRACT)" \
		--source "$(SOURCE)" \
		$(if $(PKG),--pkg "$(PKG)",)

new-repo: ## Direct/debug birth primitive (REPO= PKG= DESC= [PAYLOAD= PAYLOAD_CONTRACT=] [ORG=] [WORK_DIR=] [NO_REMOTE=1])
	@test -n "$(REPO)" || (echo "usage: make new-repo REPO=<name> PKG=<pkg> DESC=<text> [PAYLOAD=<dir>]" >&2; exit 2)
	@test -n "$(PKG)"  || (echo "usage: make new-repo REPO=<name> PKG=<pkg> DESC=<text> [PAYLOAD=<dir>]" >&2; exit 2)
	@test -n "$(DESC)" || (echo "usage: make new-repo REPO=<name> PKG=<pkg> DESC=<text> [PAYLOAD=<dir>]" >&2; exit 2)
	$(PYTHON) scripts/birth-runner/new_repo.py \
		--repo "$(REPO)" \
		--pkg "$(PKG)" \
		--desc "$(DESC)" \
		$(if $(ORG),--org "$(ORG)",) \
		$(if $(PAYLOAD),--payload "$(PAYLOAD)",) \
		$(if $(PAYLOAD_CONTRACT),--payload-contract "$(PAYLOAD_CONTRACT)",) \
		$(if $(PRODUCT_BIRTH_BINDING),--product-birth-binding "$(PRODUCT_BIRTH_BINDING)",) \
		$(if $(PRODUCT_MANIFEST),--product-manifest "$(PRODUCT_MANIFEST)",) \
		$(if $(SEMANTIC_COMPILER_SRC),--semantic-compiler-src "$(SEMANTIC_COMPILER_SRC)",) \
		$(if $(WORK_DIR),--work-dir "$(WORK_DIR)",) \
		$(if $(ORG_PROFILE_SRC),--org-profile-src "$(ORG_PROFILE_SRC)",) \
		$(if $(CLASS),--repo-class "$(CLASS)",) \
		$(if $(RECEIPT),--receipt "$(RECEIPT)",) \
		$(if $(PRIVATE),--private,) \
		$(if $(NO_REMOTE),--no-remote,)

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
	$(PYTHON) scripts/bootstrap_rename.py --pkg $(PKG) $(if $(and $(ORG),$(REPO)),--org $(ORG) --repo $(REPO),)
	@if command -v uv >/dev/null 2>&1; then \
		uv sync --extra dev || (echo "uv sync failed — not falling back to pip" >&2; exit 1); \
	else \
		$(PYTHON) -m pip install -e ".[dev]"; \
	fi
	$(PYTHON) scripts/render_cursor_rules.py --force

pr-check: verify ## In-repo product gate (OPEN_PR stays 0; use gov-pr to open)
	@if command -v uv >/dev/null 2>&1; then \
		uv lock --check || (echo "uv lock --check failed — lock state is stale" >&2; exit 1); \
	else \
		echo "uv not installed — skipping lock validation"; \
	fi
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
