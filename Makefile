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
PYTHON := $(shell bash -c 'source "$$PWD/scripts/dev-harness/_resolve_python.sh"; dev_harness_python')
else
PYTHON ?= $(shell bash -c 'source "$$PWD/scripts/dev-harness/_resolve_python.sh"; dev_harness_python')
endif
# Export so recipes use $$PYTHON (shell variable expansion) instead of $(PYTHON)
# (Make text interpolation). Shell variable expansion treats the resolved path
# as data and cannot be broken by quote or command-substitution characters in
# the checkout root, unlike Make interpolation into recipe shell text.
export PYTHON
DESKTOP_USER ?= alice
DESKTOP_APP_NAME ?=
CHAT_FIRST_E2E_ACTION ?= prepare
CHAT_FIRST_E2E_CASE ?= enabled
CHAT_FIRST_E2E_SECONDS ?= 86400

.PHONY: setup setup-main setup-hooks setup-backend preflight runtime-image-source-closure runtime-image-smoke dev-check dev-up dev-status dev-summary dev-reset dev-down dev-logs dev dev-desktop dev-init dev-verify list-memory-scenarios seed-memory-scenario reset-memory-scenario desktop-run-local chat-first-e2e-fixture run-canonical-promotion run-canonical-maintenance

# Baseline setup is deliberately limited to prerequisites that the default
# pre-push gate may require; app and desktop runtime environments stay opt-in.
setup: setup-main setup-hooks setup-backend
	@echo "Worktree setup complete: hooks installed and backend pre-push environment ready."

setup-main:
	@bash scripts/setup-refresh-main.sh

setup-hooks:
	@bash scripts/install-git-hooks.sh

setup-backend:
	@bash backend/scripts/sync-python-deps.sh

preflight:
	python3 .github/scripts/pr_preflight.py --lane local --base origin/main

runtime-image-source-closure:
	python3 backend/scripts/runtime_image_contracts.py check

runtime-image-smoke:
	@test -n "$(SERVICE)" || (echo "SERVICE is required (for example: make runtime-image-smoke SERVICE=pusher)" >&2; exit 2)
	python3 backend/scripts/runtime_image_contracts.py build-smoke --service "$(SERVICE)" --image "$(or $(IMAGE),omi-$(SERVICE):dev)"

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
	"$$PYTHON" scripts/dev-harness/list-memory-scenarios.py

seed-memory-scenario:
	"$$PYTHON" scripts/dev-harness/seed-memory-scenario.py $(SCENARIO)

reset-memory-scenario:
	"$$PYTHON" scripts/dev-harness/reset-memory-scenario.py $(SCENARIO)

desktop-run-local:
	@if [ -n "$(DESKTOP_APP_NAME)" ]; then \
		PYTHON="$$PYTHON" OMI_APP_NAME="$(DESKTOP_APP_NAME)" bash scripts/dev-harness/desktop-run-local.sh "$(DESKTOP_USER)"; \
	else \
		PYTHON="$$PYTHON" bash scripts/dev-harness/desktop-run-local.sh "$(DESKTOP_USER)"; \
	fi

chat-first-e2e-fixture:
	PYTHON="$(PYTHON)" bash scripts/dev-harness/chat-first-e2e-fixture.sh "$(CHAT_FIRST_E2E_ACTION)" "$(CHAT_FIRST_E2E_CASE)" "$(CHAT_FIRST_E2E_SECONDS)"

run-canonical-promotion:
	PYTHON="$$PYTHON" PYTHONPATH="scripts/dev-harness:backend$(if $(PYTHONPATH),:$(PYTHONPATH),)" "$$PYTHON" scripts/dev-harness/run-canonical-promotion.py "$(PROMOTION_USER)"

run-canonical-maintenance:
	PYTHON="$$PYTHON" PYTHONPATH="scripts/dev-harness:backend$(if $(PYTHONPATH),:$(PYTHONPATH),)" "$$PYTHON" scripts/dev-harness/run-canonical-maintenance.py "$(MAINTENANCE_USER)"
