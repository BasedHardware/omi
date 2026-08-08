#!/usr/bin/env bash
# Publish one explicit production Agent VM canary migration artifact.
set -euo pipefail

approval_policy="state-preserving-v1"
if [[ "${AGENT_VM_MIGRATION_APPLY:-}" != "1" || "${AGENT_VM_MIGRATION_APPROVAL_POLICY:-}" != "$approval_policy" ]]; then
  echo "REFUSED: set AGENT_VM_MIGRATION_APPLY=1 and AGENT_VM_MIGRATION_APPROVAL_POLICY=${approval_policy}." >&2
  exit 1
fi

project="${AGENT_VM_MIGRATION_PROJECT:-}"
bucket="${AGENT_VM_MIGRATION_BUCKET:-}"
manifest="${AGENT_VM_MIGRATION_MANIFEST:-}"
expected_generation="${AGENT_VM_MIGRATION_EXPECTED_ACTIVE_GENERATION:-}"
region="${AGENT_VM_MIGRATION_REGION:-us-central1}"
scheduler="${AGENT_VM_MIGRATION_SCHEDULER:-agent-vm-reconciler-5m}"
if [[ "$project" != "based-hardware" || "$bucket" != "based-hardware-agent" || ! -f "$manifest" ]]; then
  echo "Production project based-hardware, bucket based-hardware-agent, and an existing migration manifest are required." >&2
  exit 2
fi
if [[ ! "$expected_generation" =~ ^[1-9][0-9]*$ ]]; then
  echo "AGENT_VM_MIGRATION_EXPECTED_ACTIVE_GENERATION must be the inspected nonzero active-pointer generation." >&2
  exit 2
fi

# Production activation is staged while the scheduler is paused. This keeps
# pointer publication separate from the deliberate first canary execution.
scheduler_state="$(
  gcloud scheduler jobs describe "$scheduler" \
    --project="$project" --location="$region" --format='value(state)' 2>/dev/null || true
)"
if [[ "$scheduler_state" != "PAUSED" ]]; then
  echo "ERROR: production reconciler scheduler ${scheduler} must exist and be PAUSED before activation." >&2
  exit 2
fi

project_number="$(gcloud projects describe "$project" --format='value(projectNumber)' 2>/dev/null || true)"
bucket_project_number="$(
  curl --fail --silent --show-error \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://storage.googleapis.com/storage/v1/b/${bucket}?fields=projectNumber" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin).get("projectNumber", ""))' \
    2>/dev/null || true
)"
if [[ ! "$project_number" =~ ^[0-9]+$ || "$bucket_project_number" != "$project_number" ]]; then
  echo "ERROR: bucket gs://${bucket} does not belong to production project ${project}." >&2
  exit 2
fi

manifest_sha="$(
  python3 - "$manifest" "$approval_policy" <<'PY'
import hashlib
import json
import sys

path, approval_policy = sys.argv[1:]
raw = json.load(open(path, encoding="utf-8"))
declared = raw.pop("manifestSha256", None)
canonical = (json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n").encode()
migration = raw.get("bootImageMigration")
allowed = migration.get("allowedUids") if isinstance(migration, dict) else None
if (
    raw.get("environment") != "production"
    or not isinstance(declared, str)
    or declared != hashlib.sha256(canonical).hexdigest()
    or not isinstance(migration, dict)
    or migration.get("enabled") is not True
    or not isinstance(allowed, list)
    or len({uid.strip() for uid in allowed if isinstance(uid, str) and uid.strip()}) != 1
    or len(allowed) != 1
    or migration.get("maxConcurrency") != 1
    or migration.get("drainRunning") is not True
    or migration.get("approvalPolicy") != approval_policy
    or not isinstance(migration.get("soakSeconds"), int)
    or migration["soakSeconds"] < 10 * 60
    or not isinstance(migration.get("retentionSeconds"), int)
    or migration["retentionSeconds"] < 7 * 24 * 60 * 60
    or not str(raw.get("imageDigest", "")).startswith("gcr.io/based-hardware/agent-vm")
    or not str(raw.get("startupUri", "")).startswith("gs://based-hardware-agent/agent-vm/releases/")
    or not str(raw.get("bootImage", "")).startswith("projects/based-hardware/global/images/")
    or raw.get("serviceAccount") != "omi-agent-vm-bootstrap@based-hardware.iam.gserviceaccount.com"
):
    raise SystemExit("migration manifest is not a canonical production state-preserving canary plan")
print(declared)
PY
)"

active_uri="gs://${bucket}/agent-vm/releases/active.json"
previous_uri="gs://${bucket}/agent-vm/releases/previous.json"
actual_generation="$(gcloud storage objects describe "$active_uri" --format='value(generation)')"
if [[ "$actual_generation" != "$expected_generation" ]]; then
  echo "ERROR: active pointer changed from expected generation ${expected_generation} to ${actual_generation}; re-inspect." >&2
  exit 1
fi

active_readback="$(mktemp)"
migration_readback="$(mktemp)"
pointer_error="$(mktemp)"
trap 'rm -f "$active_readback" "$migration_readback" "$pointer_error"' EXIT
gcloud storage cp "${active_uri}#${expected_generation}" "$active_readback"

# The migration artifact may add only the hash-covered migration section to
# the exact active normal release. It cannot smuggle a stale image or runtime.
python3 - "$active_readback" "$manifest" <<'PY'
import json
import sys

active = json.load(open(sys.argv[1], encoding="utf-8"))
candidate = json.load(open(sys.argv[2], encoding="utf-8"))
if "bootImageMigration" in active:
    raise SystemExit("active production pointer already contains a migration plan")
for payload in (active, candidate):
    payload.pop("manifestSha256", None)
candidate.pop("bootImageMigration", None)
if candidate != active:
    raise SystemExit("production migration must extend the exact active normal release")
PY

manifest_uri="gs://${bucket}/agent-vm/migrations/${manifest_sha}.json"
gcloud storage cp --no-clobber "$manifest" "$manifest_uri"
gcloud storage cp "$manifest_uri" "$migration_readback"
cmp -s "$manifest" "$migration_readback"

if previous_generation="$(gcloud storage objects describe "$previous_uri" --format='value(generation)' 2>"$pointer_error")"; then
  [[ "$previous_generation" =~ ^[0-9]+$ ]]
elif grep -Eq '(^|[^-0-9])404([^0-9]|$)|NOT_FOUND' "$pointer_error"; then
  previous_generation=0
else
  cat "$pointer_error" >&2
  echo "ERROR: previous Agent VM manifest pointer could not be read." >&2
  exit 1
fi
gcloud storage cp "${active_uri}#${expected_generation}" "$previous_uri" \
  --cache-control='no-store,max-age=0' --if-generation-match="$previous_generation"
gcloud storage cp "$manifest_uri" "$active_uri" \
  --cache-control='no-store,max-age=0' --if-generation-match="$expected_generation"
activated_generation="$(gcloud storage objects describe "$active_uri" --format='value(generation)')"
[[ "$activated_generation" =~ ^[0-9]+$ ]]
gcloud storage cp "${active_uri}#${activated_generation}" "$migration_readback"
cmp -s "$manifest" "$migration_readback"
echo "Activated production Agent VM canary manifest ${manifest_sha} at generation ${activated_generation}; scheduler remains PAUSED."
