PYTHON ?= $(shell if [ -x backend/venv/bin/python ]; then printf backend/venv/bin/python; else printf python3; fi)
DESKTOP_USER ?= alice

.PHONY: dev-check dev-up dev-status dev-summary dev-reset dev-down dev-logs dev dev-desktop dev-init dev-verify list-v17-scenarios seed-v17-scenario reset-v17-scenario desktop-run-local

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

list-v17-scenarios:
	$(PYTHON) scripts/dev-harness/list-v17-scenarios.py

seed-v17-scenario:
	$(PYTHON) scripts/dev-harness/seed-v17-scenario.py $(SCENARIO)

reset-v17-scenario:
	$(PYTHON) scripts/dev-harness/reset-v17-scenario.py $(SCENARIO)

desktop-run-local:
	PYTHON="$(PYTHON)" bash scripts/dev-harness/desktop-run-local.sh "$(DESKTOP_USER)"
