#!/usr/bin/env bash
# LIFECYCLE: permanent
# Run canonical-memory, task and record-admission Firestore emulator proofs.
#
# These are the strongest correctness evidence the memory system has: they
# exercise crash recovery, deletion races, account-generation contention, day
# rollover, overlapping runners and writer cutover against a real Firestore
# emulator, which unit tests with fakes cannot reach.
#
# Expects a Firestore emulator already listening; run under
# `firebase emulators:exec --only firestore --project demo-omi-isolated-tests`, which
# exports FIRESTORE_EMULATOR_HOST from firebase.json (127.0.0.1:8085).
#
# The environment below mirrors _subprocess_env() in
# Local emulator proofs use synthetic owners only. MEMORY_ENABLED=on is required:
# the production canonical-intake fence defaults to off, and without it every
# write-path scenario fails closed with CanonicalMemoryIntakePausedError, which
# is a harness precondition rather than a defect.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_DIR"

if [[ -z "${FIRESTORE_EMULATOR_HOST:-}" ]]; then
  echo "FIRESTORE_EMULATOR_HOST is required; run this under 'firebase emulators:exec'" >&2
  exit 2
fi

PYTHON="${PYTHON:-python}"

export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-demo-omi-isolated-tests}"
export GCLOUD_PROJECT="$GOOGLE_CLOUD_PROJECT"
export FIREBASE_PROJECT_ID="$GOOGLE_CLOUD_PROJECT"
export PROVIDER_MODE=offline
export MEMORY_ENABLED=on
export ENCRYPTION_SECRET="${ENCRYPTION_SECRET:-omi_emulator_proof_key_32_bytes_ok}"  # pragma: allowlist secret
export GOOGLE_AUTH_DISABLE_GCE_CHECK=true
export GCE_METADATA_HOST=127.0.0.1:9
export NO_PROXY=127.0.0.1,localhost,::1
export no_proxy="$NO_PROXY"

failures=()

run_proof() {
  local label="$1"
  shift
  echo "::group::${label}"
  if "$@"; then
    echo "PASS ${label}"
  else
    echo "FAIL ${label}"
    failures+=("$label")
  fi
  echo "::endgroup::"
}

# These require real transaction retries and the lifecycle network guard;
# ordinary unit shards intentionally do not stand up emulator services.
run_proof "v3 Finish (bounded source query and concurrent window fence)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_conversations_v3_finish_emulator.py
run_proof "PL-158 quiet discovery and admission speech clock" \
  env GOOGLE_CLOUD_PROJECT=demo-pl158-quiet-clock GCLOUD_PROJECT=demo-pl158-quiet-clock FIREBASE_PROJECT_ID=demo-pl158-quiet-clock \
  "$PYTHON" -m scripts.quiet_speech_clock_emulator_test
run_proof "record custody append (committed reply loss, retries, privacy)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_record_custody_append_emulator.py
run_proof "LLM gateway idempotency (claim, replay, expiry, stale settlement)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_llm_gateway_idempotency_firestore.py
run_proof "record nojob seal (synthetic cleanup ownership)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/unit/test_record_seal_nojob_emulator.py
run_proof "age-gate unpark (paging, CAS and durable enqueue debt)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/unit/test_enrichment_age_gate_unpark_emulator.py
run_proof "lifecycle properties (real Firestore, named producer exits)" \
  "$PYTHON" -m testing.lifecycle_sim.run \
  --extra-test-module testing/lifecycle_properties/test_properties.py


run_proof "sync/live overlap admission race (coarse hint, contention retry, no twin)" \
  "$PYTHON" scripts/sync_live_overlap_contention_emulator_test.py
run_proof "canonical apply-control read retry (transient / exhausted / wipe race)" \
  "$PYTHON" scripts/canonical_apply_control_retry_emulator_test.py
run_proof "memory visibility contention (materialization, fresh transactions and commit readback)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/memory_visibility_contention_emulator_test.py
run_proof "destructive gate contention (same-kind block / stale takeover fence)" \
  "$PYTHON" scripts/destructive_gate_contention_emulator_test.py
# Purge fixtures deliberately refuse cloud fallback. Make a wrong proof host a
# failure here, rather than recording a successful invocation of skipped tests.
if [[ "$FIRESTORE_EMULATOR_HOST" == 127.0.0.1:* || "$FIRESTORE_EMULATOR_HOST" == localhost:* ]]; then
  run_proof "pipeline ledger and finalization jobs (ordering and account erasure)" \
    "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_pipeline_ledger_firestore.py
  run_proof "conversation purge (coalescing, pre-PR consumers, rollback and WAL)" \
    "$PYTHON" -m pytest -q -p no:cacheprovider \
    tests/integration/test_conversation_batch_purge_emulator.py \
    tests/integration/test_conversation_purge_coalescing_emulator.py \
    tests/integration/test_conversation_purge_mixed_version_emulator.py \
    tests/unit/test_record_wal_handoff_emulator.py
else
  echo "FAIL account and conversation erasure proofs: a loopback Firestore emulator is required" >&2
  failures+=("account and conversation erasure proofs: loopback emulator required")
fi
run_proof "ledger correction, revert, standalone reopen, privacy fence" \
  "$PYTHON" scripts/knowledge_ledger_correction_emulator_test.py
# Module execution, not a file path: this older proof has no sys.path bootstrap
# and relies on backend/ staying the import root.
run_proof "writer cutover / rollback / rollforward" \
  "$PYTHON" -m scripts.knowledge_ledger_writer_transition_emulator_test
run_proof "summary task recovery, concurrency and expiry" \
  "$PYTHON" -m pytest \
  tests/integration/test_summary_debt_repair_firestore.py \
  tests/integration/test_summary_task_promotion_emulator.py \
  tests/integration/test_candidate_accept_expiry_emulator.py -q
run_proof "v3 reconcile write elision (unchanged pass, Home receipts, kill switch)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_conversations_v3_unchanged_writes_firestore.py
# The regression guards only. The full cost matrix (the 1,976- and 1,645-row shapes) runs locally with
# V3_CLOSURE_COST_REPORT set; see the test module docstring.
run_proof "v3 locked-closure allowance (heavy closure custody, kill switches, batch cap, per-batch lease renewal, refinement)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_conversations_v3_locked_closure_cost_firestore.py \
  -k "rows_1156_sources_20 or kill_switch or outlives_its_lease or batch_cap or four_line_windows"
run_proof "desktop screen sync frame request delivery, expiry and quota" \
  "$PYTHON" -m pytest -q tests/integration/test_screen_sync_frame_queue_emulator.py

# Silent receipts can become ready at assignment; keep the paginated follow-up
# and mixed-completion read guards in the hosted emulator acceptance suite.
run_proof "batch projection follow-up (silent ready, rollback and mixed completion)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider \
  tests/integration/test_batch_pipeline_projection_followup_firestore.py \
  tests/integration/test_batch_pipeline_silence_sizing_firestore.py

run_proof "held-partial cursor concurrency (advance and wrap fence)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_held_partial_cursor_emulator.py

run_proof "projection ghost-hold release gaps and ready-hint repair follow-up" \
  "$PYTHON" -m pytest -q -rxX -p no:cacheprovider \
  tests/integration/test_batch_projection_ghost_holds_firestore.py

run_proof "record replay (capture, admission, titling and scoped receipts)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_replay_harness_firestore.py \
  tests/integration/test_replay_harness_titling_firestore.py

# The committed 120-transition privacy smoke plus mutation controls; the full
# qualification corpus stays on the explicit heavy-lane Make target.
run_proof "privacy cache replay (120-transition smoke and catch proofs)" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_replay_harness_privacy_firestore.py

# Job-store conformance (legacy-retire lane 12): sim + Firestore emulator legs here; the Postgres leg
# skips in CI (no Postgres service, decision S6) and is proven locally/staging.
# Includes PL-141/142/143 scheduler pull ownership, expiry and abort/restart recovery, and committed projection debt (PL-665/666/667).
run_proof "job-store conformance (fenced pulls, projection scan fallback, custody and projection obligations)" \
  env "OMI_REQUIRE_STORE_BACKENDS=${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_store_conformance.py \
  tests/integration/test_recovery_custody_conformance.py

run_proof "allowance parking migration (owner concurrency, retry pacing, privacy and replay)" \
  env "OMI_REQUIRE_STORE_BACKENDS=${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_batch_allowance_holds.py -k migration
run_proof "allowance-held recording release and transcript delivery" \
  "$PYTHON" -m pytest -q -p no:cacheprovider \
  tests/integration/test_batch_pipeline_live_firestore.py::test_allowance_held_recording_releases_and_publishes_one_transcript

# Daily parity: real claims/settlement on old Firestore and new Postgres.
# CI requires sim + emulator; local/staging qualification must require all.
run_proof "enrichment recovery conformance (PL-342/397/398)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" OMI_ENV_STAGE=offline \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/enrichment_recovery_emulator_test.py

# Real delivery/settlement on old and replacement stores, with virtual budget
# and heartbeat schedules. CI requires sim + emulator; local/staging qualification
# must set OMI_REQUIRE_STORE_BACKENDS=all so Postgres is required too.
run_proof "enrichment budget and hold-cap conformance (PL-420/421)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" OMI_ENV_STAGE=offline \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/enrichment_budget_emulator_test.py

# PL-439: a derived-refresh race keeps the same retryable delivery. CI requires
# sim + emulator; complete local/staging qualification requires all three stores.
run_proof "enrichment revision-race conformance (PL-439)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" OMI_ENV_STAGE=offline \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/enrichment_revision_emulator_test.py

# PL-426: local silence survives storage failure without paid/vendor-health debt.
# CI requires sim/emulator; full local qualification also requires Postgres.
run_proof "provider local-silence crash conformance (PL-426)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" OMI_ENV_STAGE=offline \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/provider_silence_emulator_test.py

# Daily architecture parity: require both local CI backends rather than letting
# a missing emulator look green. Local/staging runs require all three stores.
run_proof "recovery/admission parity PL-057/072/086 (sim + emulator)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_recovery_admission_conformance.py

# PL-042: the same durable-enqueue invariant over the old and new outboxes.
# This script selects the existing proof workflow; require its available legs
# rather than allowing a missing emulator to produce a passing skipped matrix.
run_proof "PL-042 outbox durability (sim + emulator required; Postgres when available)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_parity_outbox_durability.py

# PL-194: a later failed pull returns all earlier committed leases. Require both
# local legs in CI; local qualification uses =all to require Postgres as well.
run_proof "partial-pull conformance (PL-194, sim + emulator required)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_partial_pull_conformance.py

# Daily parity PL-396/105/363. A missing old store must fail this qualification;
# Postgres is additionally required by the all-backend local invocation.
run_proof "held-custody conformance (sim + emulator required)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_held_custody_conformance.py

run_proof "pull batch parity (PL-321/322/323, sim + emulator required)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_pull_batch_parity.py

# PL-211: every replacement Store must preserve pending-deletion and restore
# semantics. Missing mandatory local backends are failures, never silent skips.
run_proof "pending deletion and restore conformance (sim + emulator required)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider tests/integration/test_pending_deletion_conformance.py

# Daily parity PL-583/584/585: admission, settle clocks and fresh/backlog isolation.
# The stage interface is shared; carrier binding and owner discovery stay separate.
run_proof "provider merge conformance (sim + emulator required; Postgres when available)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/provider_merge_emulator_test.py

# PL-606/607/608: independent projection clocks cannot hide owed follow-ups.
run_proof "projection discovery conformance (sim + emulator required; Postgres when available)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/projection_discovery_emulator_test.py

run_proof "stale merge-head promotion (real transactions, privacy fence, stale hints, demotion)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/merge_stale_head_emulator_test.py

# Daily parity PL-631/632/633: older copiers, incapable mergers and same-slot redrive.
run_proof "result protocol conformance (sim + emulator required; Postgres when available)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/result_protocol_emulator_test.py

run_proof "Firestore read budget: batch unit end-to-end (M3 scenario 1)" \
  "$PYTHON" -m pytest -q -s -p no:cacheprovider tests/integration/test_firestore_read_budget_batch_unit.py
run_proof "Firestore read budget: conversation list page (M3 scenario 3)" \
  "$PYTHON" -m pytest -q -s -p no:cacheprovider tests/integration/test_firestore_read_budget_conversation_page.py
run_proof "Firestore read budget: sync upload, privacy and status polls" \
  "$PYTHON" -m pytest -q -s -p no:cacheprovider tests/integration/test_firestore_read_budget_sync.py
run_proof "Firestore read budget: idle projection and pending-work backlog" \
  "$PYTHON" -m pytest -q -s -p no:cacheprovider tests/integration/test_firestore_read_budget_idle.py

# PL-487/482: durable record settlement and pacing use the real Store on every
# backend. CI requires sim/emulator; full local qualification requires =all.
run_proof "record dead-letter and retry conformance (PL-487/482)" \
  env OMI_REQUIRE_STORE_BACKENDS="${OMI_REQUIRE_STORE_BACKENDS:-sim,emulator}" OMI_ENV_STAGE=offline \
  "$PYTHON" -m pytest -q -p no:cacheprovider scripts/record_dead_letter_emulator_test.py

if (( ${#failures[@]} )); then
  echo
  echo "Emulator proofs failed: ${#failures[@]}"
  for name in "${failures[@]}"; do
    echo "  - ${name}"
  done
  exit 1
fi

echo
echo "All emulator proofs passed."
