#!/usr/bin/env bash
# Restore the last accepted Agent VM release pointer. Refuse by default.
set -euo pipefail

if [[ "${AGENT_VM_RELEASE_ROLLBACK:-}" != "1" ]]; then
  echo "REFUSED: set AGENT_VM_RELEASE_ROLLBACK=1 to restore the previous Agent VM release." >&2
  exit 1
fi

bucket="${AGENT_VM_RECONCILER_BUCKET:-}"
if [[ -z "$bucket" ]]; then
  echo "AGENT_VM_RECONCILER_BUCKET is required." >&2
  exit 2
fi

active="gs://${bucket}/agent-vm/releases/active.json"
previous="gs://${bucket}/agent-vm/releases/previous.json"
error_file="$(mktemp)"
trap 'rm -f "$error_file"' EXIT

if ! active_generation="$(gcloud storage objects describe "$active" --format='value(generation)' 2>"$error_file")"; then
  cat "$error_file" >&2
  echo "REFUSED: active Agent VM release pointer could not be read; rollback state is unchanged." >&2
  exit 1
fi
if ! previous_generation="$(gcloud storage objects describe "$previous" --format='value(generation)' 2>"$error_file")"; then
  cat "$error_file" >&2
  echo "REFUSED: previous Agent VM release pointer could not be read; rollback state is unchanged." >&2
  exit 1
fi

# Read the exact prior object version, then atomically replace only the active
# generation observed above.  A concurrent deployment or rollback fails rather
# than overwriting its pointer.
gcloud storage cp "${previous}#${previous_generation}" "$active" \
  --cache-control='no-store,max-age=0' --if-generation-match="$active_generation"
echo "Restored Agent VM release pointer from ${previous} with generation guard."
