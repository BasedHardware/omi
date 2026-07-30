ifeq ($(OS),Windows_NT)
GIT_EXEC_PATH := $(shell git --exec-path)
SHELL := $(GIT_EXEC_PATH)/../../../bin/bash.exe
BASH := "$(SHELL)"
else
SHELL := bash
BASH := bash
endif

HOOKS_DIR := $(shell git rev-parse --git-path hooks)
# Retain a lazy compatibility value for callers that inspect $(PYTHON).
PYTHON ?= $(shell source scripts/dev-harness/_resolve_python.sh; dev_harness_python)
# Keep the checkout-local interpreter resolution inside Bash so native GNU
# Make never exports a Unicode checkout path through its legacy code page.
PYTHON_RUNNER := $(BASH) scripts/dev-harness/run-python.sh
DESKTOP_USER ?= alice
DESKTOP_APP_NAME ?=

.PHONY: setup setup-main setup-hooks setup-backend preflight runtime-image-source-closure runtime-image-smoke dev-check dev-up dev-status dev-summary dev-reset dev-down dev-logs dev dev-desktop dev-init dev-verify list-memory-scenarios seed-memory-scenario reset-memory-scenario desktop-run-local run-canonical-maintenance

# Baseline setup is deliberately limited to prerequisites that the default
# pre-push gate may require; app and desktop runtime environments stay opt-in.
setup: setup-main setup-hooks setup-backend
	@echo "Worktree setup complete: hooks installed and backend pre-push environment ready."

setup-main:
	@$(BASH) scripts/setup-refresh-main.sh

setup-hooks:
	@$(BASH) scripts/install-git-hooks.sh

setup-backend:
	@$(BASH) backend/scripts/sync-python-deps.sh

preflight:
	$(PYTHON_RUNNER) .github/scripts/pr_preflight.py --lane local --base origin/main

runtime-image-source-closure:
	$(PYTHON_RUNNER) backend/scripts/runtime_image_contracts.py check

runtime-image-smoke:
	@test -n "$(SERVICE)" || (echo "SERVICE is required (for example: make runtime-image-smoke SERVICE=pusher)" >&2; exit 2)
	$(PYTHON_RUNNER) backend/scripts/runtime_image_contracts.py build-smoke --service "$(SERVICE)" --image "$(or $(IMAGE),omi-$(SERVICE):dev)"

dev-check:
	$(BASH) scripts/dev-harness/dev-check.sh

dev-up:
	$(BASH) scripts/dev-harness/dev-up.sh

dev:
	$(MAKE) dev-up

dev-desktop:
	$(MAKE) dev
	$(MAKE) desktop-run-local

dev-init:
	$(BASH) scripts/dev-harness/dev-init.sh

dev-verify:
	$(BASH) scripts/dev-harness/verify-desktop-local-launch.sh

dev-status:
	$(BASH) scripts/dev-harness/dev-status.sh

dev-summary:
	$(BASH) scripts/dev-harness/dev-summary.sh

dev-reset:
	$(BASH) scripts/dev-harness/dev-reset.sh

dev-down:
	$(BASH) scripts/dev-harness/dev-down.sh

dev-logs:
	$(BASH) scripts/dev-harness/dev-logs.sh

list-memory-scenarios:
	$(PYTHON_RUNNER) scripts/dev-harness/list-memory-scenarios.py

seed-memory-scenario:
	$(PYTHON_RUNNER) scripts/dev-harness/seed-memory-scenario.py $(SCENARIO)

reset-memory-scenario:
	$(PYTHON_RUNNER) scripts/dev-harness/reset-memory-scenario.py $(SCENARIO)

desktop-run-local:
	@if [ -n "$(DESKTOP_APP_NAME)" ]; then \
		OMI_APP_NAME="$(DESKTOP_APP_NAME)" $(BASH) scripts/dev-harness/desktop-run-local.sh "$(DESKTOP_USER)"; \
	else \
		$(BASH) scripts/dev-harness/desktop-run-local.sh "$(DESKTOP_USER)"; \
	fi

run-canonical-maintenance:
	$(PYTHON_RUNNER) scripts/dev-harness/run-canonical-maintenance.py "$(MAINTENANCE_USER)"
