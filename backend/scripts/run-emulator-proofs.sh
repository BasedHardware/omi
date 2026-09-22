#!/usr/bin/env bash
# LIFECYCLE: permanent
# Run the canonical-memory / JIT Firestore emulator proofs.
#
# These are the strongest correctness evidence the memory system has: they
# exercise crash recovery, deletion races, account-generation contention, day
# rollover, overlapping runners and writer cutover against a real Firestore
# emulator, which unit tests with fakes cannot reach.
#
# Until 2026-08-30 nothing ran them automatically. The daily-sweep crash-replay
# proof was red on main from the day #12084 introduced it, while
# .github/failure-classes/FC-daily-memory-sweep-fence.json named that very file
# as its canonical prevention artifact -- so the registry read as covered while
# the guard was never executed. A guard artifact CI does not run is worse than
# no guard, because it is counted as coverage.
#
# Expects a Firestore emulator already listening; run under
# `firebase emulators:exec --only firestore --project demo-omi-jit-qa`, which
# exports FIRESTORE_EMULATOR_HOST from firebase.json (127.0.0.1:8085).
#
# The environment below mirrors _subprocess_env() in
# backend/scripts/jit_qa_orchestrated_dogfood.py. MEMORY_MODE=read is required:
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

export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-demo-omi-jit-qa}"
export GCLOUD_PROJECT="$GOOGLE_CLOUD_PROJECT"
export FIREBASE_PROJECT_ID="$GOOGLE_CLOUD_PROJECT"
export PROVIDER_MODE=offline
export MEMORY_MODE=read
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

# Runs a proof for signal without letting it decide the lane's colour.
#
# Reserved for the arbitration proof, which is intermittent against a freshly
# started emulator. It deliberately runs concurrent transactions to prove
# cross-device reservation, and a cold Firestore emulator sometimes loses them:
# `google.api_core.exceptions.Aborted: 409 Transaction lock timeout` surfacing
# as `ValueError: Failed to commit transaction in 5 attempts`. That is an
# emulator limit, not an assertion failure -- when it completes it reports
# correct semantics (`planned=['reserved','rejected']`,
# `full_turns=['rejected','reserved']`).
#
# Measured 2026-08-30: 3/3 passes against a long-warmed emulator; then two
# consecutive failures and one pass under fresh `emulators:exec`, including a
# failure when run alone, so it is not accumulated state from earlier proofs.
# Warm-up appears to matter, but the evidence is a handful of runs, not a
# characterisation -- treat that as the leading hypothesis, not the cause.
#
# Making it fatal would redden the lane unpredictably, and a lane that fails for
# reasons nobody trusts is one nobody reads -- the exact failure this lane exists
# to correct. Making it silent would lose the signal. So it runs, it reports, and
# it does not gate. Characterise the contention (warm-up transaction, or a larger
# transaction retry budget under the emulator), then move it back to run_proof.
run_proof_for_signal_only() {
  local label="$1"
  shift
  echo "::group::${label} [non-gating]"
  if "$@"; then
    echo "PASS ${label} (non-gating -- intermittent, so one pass is not evidence the contention is gone)"
  else
    echo "::warning::${label} failed -- known intermittent emulator transaction contention, not gating this lane"
  fi
  echo "::endgroup::"
}

run_proof "daily-sweep (crash / deletion / generation / paid-wipe)" \
  "$PYTHON" scripts/daily_memory_sweep_emulator_test.py
run_proof "ledger correction, revert, standalone reopen, privacy fence" \
  "$PYTHON" scripts/knowledge_ledger_correction_emulator_test.py
run_proof "direct-user ledger API writes / lifecycle / batch fence" \
  "$PYTHON" scripts/jit_ledger_user_write_emulator_test.py
run_proof_for_signal_only "planned + ambient proactivity arbitration" \
  "$PYTHON" scripts/jit_proactivity_reservation_emulator_test.py
# Module execution, not a file path: this older proof has no sys.path bootstrap
# and relies on backend/ staying the import root.
run_proof "writer cutover / rollback / rollforward" \
  "$PYTHON" -m scripts.knowledge_ledger_writer_transition_emulator_test

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
