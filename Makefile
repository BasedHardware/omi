ROOT := $(shell git rev-parse --show-toplevel)
HOOKS_DIR := $(shell git rev-parse --git-path hooks)
PYTHON ?= $(shell if [ -x backend/venv/bin/python ]; then printf backend/venv/bin/python; else printf python3; fi)
DESKTOP_USER ?= alice
DESKTOP_APP_NAME ?=

.PHONY: setup setup-main setup-hooks preflight dev-check dev-up dev-status dev-summary dev-reset dev-down dev-logs dev dev-desktop dev-init dev-verify list-memory-scenarios seed-memory-scenario reset-memory-scenario desktop-run-local run-canonical-promotion

setup: setup-main setup-hooks
	@echo "Worktree setup complete."

setup-main:
	@bash scripts/setup-refresh-main.sh

setup-hooks:
	@bash scripts/install-git-hooks.sh

preflight:
	python3 .github/scripts/pr_preflight.py --lane local --base origin/main

dev-check:
	bash scripts/dev-harness/dev-check.sh

dev-up:
	bash scripts/dev-harness/dev-up.sh

dev:
	$(MAKE) dev-up

dev-desktop:
	$(MAKE) dev
	$(MAKE) desktop-run-local

dev-init:
	bash scripts/dev-harness/dev-init.sh

dev-verify:
	bash scripts/dev-harness/verify-desktop-local-launch.sh

dev-status:
	bash scripts/dev-harness/dev-status.sh

dev-summary:
	bash scripts/dev-harness/dev-summary.sh

dev-reset:
	bash scripts/dev-harness/dev-reset.sh

dev-down:
	bash scripts/dev-harness/dev-down.sh

dev-logs:
	bash scripts/dev-harness/dev-logs.sh

list-memory-scenarios:
	$(PYTHON) scripts/dev-harness/list-memory-scenarios.py

seed-memory-scenario:
	$(PYTHON) scripts/dev-harness/seed-memory-scenario.py $(SCENARIO)

reset-memory-scenario:
	$(PYTHON) scripts/dev-harness/reset-memory-scenario.py $(SCENARIO)

desktop-run-local:
	@if [ -n "$(DESKTOP_APP_NAME)" ]; then \
		PYTHON="$(PYTHON)" OMI_APP_NAME="$(DESKTOP_APP_NAME)" bash scripts/dev-harness/desktop-run-local.sh "$(DESKTOP_USER)"; \
	else \
		PYTHON="$(PYTHON)" bash scripts/dev-harness/desktop-run-local.sh "$(DESKTOP_USER)"; \
	fi

run-canonical-promotion:
	PYTHON="$(PYTHON)" PYTHONPATH="scripts/dev-harness:backend$(if $(PYTHONPATH),:$(PYTHONPATH),)" $(PYTHON) scripts/dev-harness/run-canonical-promotion.py "$(PROMOTION_USER)"
