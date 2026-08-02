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

test:
	cd app && $(FLUTTER) test \
		test/self_hosted/cloudflare/cloudflare_transcript_api_test.dart \
		test/self_hosted/cloudflare/cloudflare_transcript_configuration_test.dart \
		test/self_hosted/cloudflare/cloudflare_transcript_provider_test.dart \
		test/self_hosted/cloudflare/cloudflare_transcripts_page_test.dart \
		test/self_hosted/sync/self_hosted_wal_sync_adapter_test.dart
	cd app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=https://worker.example.com \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN='   ' \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=false \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=whitespace-token
	cd app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=not-a-url \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=false \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=malformed-url
	cd app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=http://worker.example.com \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=false \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=public-http
	cd app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=https://worker.example.com \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=true \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=valid-https
	cd app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=true \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=http://127.0.0.1:8787 \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=true \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=loopback-http
	cd app && $(FLUTTER) test test/self_hosted/sync/self_hosted_wal_sync_adapter_environment_test.dart \
		--dart-define=BRAINBASE_SELF_HOSTED_SYNC=false \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_URL=https://worker.example.com \
		--dart-define=BRAINBASE_SELF_HOSTED_WORKER_TOKEN=token \
		--dart-define=WAL_ADAPTER_EXPECTED_ENABLED=false \
		--dart-define=WAL_ADAPTER_TEST_SCENARIO=sync-flag-disabled

integration: test

# Hermetic end-to-end replay of the Flutter read slice. This is intentionally
# separate from deployed Worker and physical-iPhone evidence.
e2e: integration

typecheck:
	cd app && $(FLUTTER) analyze \
		lib/self_hosted \
		lib/pages/conversations/widgets/conversations_section_header.dart \
		test/self_hosted

# Canonical, hermetic failure-mode probes for VibePro evidence. They exercise
# the read adapter only; neither target deploys a Worker or mutates the WAL.
parse_failure:
	cd app && $(FLUTTER) test test/self_hosted/cloudflare/cloudflare_transcript_api_test.dart \
		--plain-name 'rejects malformed JSON from the Worker list fixture without exposing the token'

schema_failure:
	cd app && $(FLUTTER) test test/self_hosted/cloudflare/cloudflare_transcript_api_test.dart \
		--plain-name 'rejects a non-object session in the Worker list response'

failure_mode_coverage: parse_failure schema_failure

cloudflare_transcript_api_test \
cloudflare_transcript_configuration_test \
cloudflare_transcript_provider_test \
cloudflare_transcripts_page_test \
self_hosted_wal_sync_adapter_test: test
