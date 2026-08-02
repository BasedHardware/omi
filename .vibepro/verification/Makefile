.PHONY: test integration e2e typecheck \
	cloudflare_transcript_api_test \
	cloudflare_transcript_configuration_test \
	cloudflare_transcript_provider_test \
	cloudflare_transcripts_page_test \
	self_hosted_wal_sync_adapter_test \
	parse_failure \
	schema_failure \
	failure_mode_coverage

FLUTTER := /Users/ksato/.local/share/flutter-3.41.9/bin/flutter
REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
INTEGRATION_BASE := upstream/main
INTEGRATION_DIFF := $(INTEGRATION_BASE)...HEAD
INTEGRATION_REQUIRED_PATHS := \
	docs/stories/omi-upstream-rebase-cloudflare-isolation.md \
	docs/specs/omi-upstream-rebase-cloudflare-isolation.md \
	docs/architecture/ADR-omi-upstream-rebase-cloudflare-isolation.md \
	docs/operational/omi-self-hosted-local-overlay.md \
	app/lib/main.dart \
	app/lib/pages/conversations/conversations_page.dart \
	app/lib/pages/conversations/widgets/conversations_section_header.dart \
	app/lib/self_hosted/cloudflare/cloudflare_transcript_api.dart \
	app/lib/self_hosted/cloudflare/cloudflare_transcript_configuration.dart \
	app/lib/self_hosted/cloudflare/cloudflare_transcript_exception.dart \
	app/lib/self_hosted/cloudflare/cloudflare_transcript_models.dart \
	app/lib/self_hosted/cloudflare/cloudflare_transcript_provider.dart \
	app/lib/self_hosted/cloudflare/cloudflare_transcripts_page.dart \
	app/lib/l10n/app_en.arb \
	app/lib/l10n/app_ja.arb \
	app/lib/l10n/app_localizations.dart \
	app/lib/l10n/app_localizations_ja.dart \
	app/test/self_hosted/cloudflare/cloudflare_transcript_api_test.dart \
	app/test/self_hosted/cloudflare/cloudflare_transcript_configuration_test.dart \
	app/test/self_hosted/cloudflare/cloudflare_transcript_provider_test.dart \
	app/test/self_hosted/cloudflare/cloudflare_transcripts_page_test.dart
INTEGRATION_FORBIDDEN_DIFF_PATTERN := (^|/)(worker|workers|ios|android|firebase)(/|$$)|(^|/)(\.env|.*\.env|secrets?|credentials?)(\..*)?$$|\.entitlements$$
INTEGRATION_MEMORIES_L10N_PATTERN := ^[+-][[:space:]]*"(alwaysInContext|baselineMemory|pinAsBaseline|unpinAsBaseline)":

test:
	cd $(REPO_ROOT)/app && $(FLUTTER) test \
		test/self_hosted/cloudflare/cloudflare_transcript_api_test.dart \
		test/self_hosted/cloudflare/cloudflare_transcript_configuration_test.dart \
		test/self_hosted/cloudflare/cloudflare_transcript_provider_test.dart \
		test/self_hosted/cloudflare/cloudflare_transcripts_page_test.dart \
		test/self_hosted/sync/self_hosted_wal_sync_adapter_test.dart
	cd $(REPO_ROOT)/app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=https://worker.example.com \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN='   ' \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=false \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=whitespace-token
	cd $(REPO_ROOT)/app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=not-a-url \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=false \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=malformed-url
	cd $(REPO_ROOT)/app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=http://worker.example.com \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=false \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=public-http
	cd $(REPO_ROOT)/app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=https://worker.example.com \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=true \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=valid-https
	cd $(REPO_ROOT)/app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=http://127.0.0.1:8787 \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=true \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=loopback-http
	cd $(REPO_ROOT)/app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=false \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=https://worker.example.com \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=false \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=sync-flag-disabled

# Reproducible evidence for the changed Cloudflare read slice. It inventories
# this exact diff and validates only the required tracked documentation, wiring,
# implementation, l10n, and focused-test surfaces before running the suite.
# It does not attest a deployed Worker or physical-iPhone end-to-end result.
integration:
	@set -eu; \
	git -C "$(REPO_ROOT)" rev-parse --verify "$(INTEGRATION_BASE)" >/dev/null; \
	echo "Integration diff inventory ($(INTEGRATION_DIFF)):"; \
	git -C "$(REPO_ROOT)" diff --name-status "$(INTEGRATION_DIFF)"; \
	git -C "$(REPO_ROOT)" diff --check "$(INTEGRATION_DIFF)"; \
	for path in $(INTEGRATION_REQUIRED_PATHS); do \
		test -f "$(REPO_ROOT)/$$path" || { echo "missing required integration surface: $$path" >&2; exit 1; }; \
	done; \
	if git -C "$(REPO_ROOT)" diff --unified=0 "$(INTEGRATION_DIFF)" -- app/lib/l10n | rg -n '$(INTEGRATION_MEMORIES_L10N_PATTERN)'; then \
		echo "unscoped Memories l10n surface in Cloudflare diff" >&2; \
		exit 1; \
	fi; \
	if git -C "$(REPO_ROOT)" diff --name-only "$(INTEGRATION_DIFF)" | rg -n '$(INTEGRATION_FORBIDDEN_DIFF_PATTERN)'; then \
		echo "forbidden Worker, native, Firebase, entitlement, or secret surface in diff" >&2; \
		exit 1; \
	fi
	$(MAKE) -C "$(REPO_ROOT)" -f "$(REPO_ROOT)/.vibepro/verification/Makefile" test

# Compatibility alias for the reproducible integration evidence above. It is
# intentionally not a deployed Worker or physical-iPhone E2E attestation.
e2e: integration

typecheck:
	cd $(REPO_ROOT)/app && $(FLUTTER) analyze \
		lib/main.dart \
		lib/pages/conversations/conversations_page.dart \
		lib/self_hosted \
		lib/pages/conversations/widgets/conversations_section_header.dart \
		test/self_hosted

# Canonical, hermetic failure-mode probes for VibePro evidence. They exercise
# the read adapter only; neither target deploys a Worker or mutates the WAL.
parse_failure:
	cd $(REPO_ROOT)/app && $(FLUTTER) test test/self_hosted/cloudflare/cloudflare_transcript_api_test.dart \
		--plain-name 'rejects malformed JSON from the Worker list fixture without exposing the token'

schema_failure:
	cd $(REPO_ROOT)/app && $(FLUTTER) test test/self_hosted/cloudflare/cloudflare_transcript_api_test.dart \
		--plain-name 'rejects a non-object session in the Worker list response'

failure_mode_coverage: parse_failure schema_failure

cloudflare_transcript_api_test \
cloudflare_transcript_configuration_test \
cloudflare_transcript_provider_test \
cloudflare_transcripts_page_test \
self_hosted_wal_sync_adapter_test: test
