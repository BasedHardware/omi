.PHONY: dev-check dev-up dev-status dev-summary dev-reset dev-down dev-logs list-v17-scenarios seed-v17-scenario reset-v17-scenario desktop-run-local

dev-check:
	bash scripts/dev-harness/dev-check.sh

dev-up:
	bash scripts/dev-harness/dev-up.sh

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
	python3 scripts/dev-harness/list-v17-scenarios.py

seed-v17-scenario:
	python3 scripts/dev-harness/seed-v17-scenario.py $(SCENARIO)

reset-v17-scenario:
	python3 scripts/dev-harness/reset-v17-scenario.py $(SCENARIO)

desktop-run-local:
	@if [ "$(origin USER)" != "command line" ]; then \
		echo "Usage: make desktop-run-local USER=<profile> (for example USER=alice)" >&2; \
		exit 2; \
	fi
	bash scripts/dev-harness/desktop-run-local.sh "$(USER)"
