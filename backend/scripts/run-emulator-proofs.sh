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
# backend/scripts/jit_qa_orchestrated_dogfood.py. MEMORY_ENABLED=on is required:
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

run_proof "daily-sweep (crash / deletion / generation / paid-wipe)" \
  "$PYTHON" scripts/daily_memory_sweep_emulator_test.py
run_proof "ledger correction, revert, standalone reopen, privacy fence" \
  "$PYTHON" scripts/knowledge_ledger_correction_emulator_test.py
run_proof "direct-user ledger API writes / lifecycle / batch fence" \
  "$PYTHON" scripts/jit_ledger_user_write_emulator_test.py
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
