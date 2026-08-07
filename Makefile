.PHONY: help doctor setup validate change-policy agent-check check test status clean reconcile push pr
PYTHON ?= python3
L9_REPO := $(PYTHON) -m tools.l9_repo --workspace "$(CURDIR)"

help:
	@$(L9_REPO) help

doctor setup validate change-policy agent-check check test status clean reconcile push pr:
	@$(L9_REPO) $@

-include Repo.mk
