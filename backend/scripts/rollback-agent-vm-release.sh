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
gcloud storage cp "$previous" "$active"
echo "Restored Agent VM release pointer from ${previous}."
