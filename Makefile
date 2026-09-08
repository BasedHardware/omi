ifeq ($(OS),Windows_NT)
GIT_EXEC_PATH := $(shell git --exec-path)
SHELL := $(GIT_EXEC_PATH)/../../../bin/bash.exe
BASH := "$(SHELL)"
else
SHELL := bash
BASH := bash
endif

HOOKS_DIR := $(shell git rev-parse --git-path hooks)
# Fall back to the working directory (where make runs, i.e. the repo root) when
# `git rev-parse --show-toplevel` cannot resolve a work tree. In a linked
# worktree whose git context resolves to a git dir rather than a work tree,
# show-toplevel exits 128 and previously expanded to an empty prefix, turning
# the source into `/scripts/dev-harness/_resolve_python.sh: No such file` and
# breaking every target. Use the make process's working directory rather than
# a command substitution: it remains shell data even when the checkout name
# contains quote or command-substitution characters.
# GNU Make supplies a built-in PYTHON=python default. Treat that as unset so
# harness targets still resolve this checkout's backend venv, while retaining
# explicit command-line and environment overrides for callers.
ifeq ($(origin PYTHON),default)
PYTHON := $(shell bash -c 'cd -P "$$PWD"; source "$$PWD/scripts/dev-harness/_resolve_python.sh"; dev_harness_python')
else
PYTHON ?= $(shell bash -c 'cd -P "$$PWD"; source "$$PWD/scripts/dev-harness/_resolve_python.sh"; dev_harness_python')
endif
# Export so recipes use $$PYTHON (shell variable expansion) instead of $(PYTHON)
# (Make text interpolation). Shell variable expansion treats the resolved path
# as data and cannot be broken by quote or command-substitution characters in
# the checkout root, unlike Make interpolation into recipe shell text.
export PYTHON
# Keep the checkout-local interpreter resolution inside Bash so native GNU
# Make never exports a Unicode checkout path through its legacy code page.
PYTHON_RUNNER := $(BASH) scripts/dev-harness/run-python.sh
DESKTOP_USER ?= alice
DESKTOP_APP_NAME ?=
CHAT_FIRST_E2E_ACTION ?= prepare
CHAT_FIRST_E2E_CASE ?= enabled
CHAT_FIRST_E2E_SECONDS ?= 86400

.PHONY: setup setup-main setup-hooks setup-backend preflight runtime-image-source-closure runtime-image-smoke dev-check dev-up dev-status dev-summary dev-reset dev-down dev-logs dev dev-desktop dev-init dev-verify list-memory-scenarios seed-memory-scenario reset-memory-scenario desktop-run-local chat-first-e2e-fixture run-canonical-maintenance

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

chat-first-e2e-fixture:
	PYTHON="$(PYTHON)" bash scripts/dev-harness/chat-first-e2e-fixture.sh "$(CHAT_FIRST_E2E_ACTION)" "$(CHAT_FIRST_E2E_CASE)" "$(CHAT_FIRST_E2E_SECONDS)"

run-canonical-maintenance:
	$(PYTHON_RUNNER) scripts/dev-harness/run-canonical-maintenance.py "$(MAINTENANCE_USER)"
