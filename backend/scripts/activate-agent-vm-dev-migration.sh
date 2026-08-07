#!/usr/bin/env bash
# Publish one explicit development-only Agent VM boot-image migration artifact.
set -euo pipefail

if [[ "${AGENT_VM_MIGRATION_APPLY:-}" != "1" ]]; then
  echo "REFUSED: set AGENT_VM_MIGRATION_APPLY=1 to activate a development Agent VM migration." >&2
  exit 1
fi

project="${AGENT_VM_MIGRATION_PROJECT:-}"
bucket="${AGENT_VM_MIGRATION_BUCKET:-}"
manifest="${AGENT_VM_MIGRATION_MANIFEST:-}"
if [[ "$project" != "based-hardware-dev" || -z "$bucket" || ! -f "$manifest" ]]; then
  echo "AGENT_VM_MIGRATION_PROJECT=based-hardware-dev, AGENT_VM_MIGRATION_BUCKET, and an existing AGENT_VM_MIGRATION_MANIFEST are required." >&2
  exit 2
fi
if [[ ! "$bucket" =~ ^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$ ]]; then
  echo "AGENT_VM_MIGRATION_BUCKET must be a valid bucket name." >&2
  exit 2
fi

# Verify the destination bucket actually belongs to the development project
# so a cross-environment value cannot poison a production manifest pointer.
project_number="$(gcloud projects describe "$project" --format='value(projectNumber)' 2>/dev/null || true)"
bucket_project_number="$(
  curl --fail --silent --show-error \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://storage.googleapis.com/storage/v1/b/${bucket}?fields=projectNumber" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin).get("projectNumber", ""))' \
    2>/dev/null || true
)"
if [[ ! "$project_number" =~ ^[0-9]+$ || "$bucket_project_number" != "$project_number" ]]; then
  echo "ERROR: bucket gs://${bucket} belongs to project number '${bucket_project_number:-unknown}', not development project '${project_number:-unknown}'; refusing cross-environment activation." >&2
  exit 2
fi

manifest_sha="$({
  python3 - "$manifest" <<'PY'
import hashlib
import json
import sys

path = sys.argv[1]
raw = json.load(open(path, encoding="utf-8"))
declared = raw.pop("manifestSha256", None)
canonical = (json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n").encode()
migration = raw.get("bootImageMigration")
allowed = migration.get("allowedUids") if isinstance(migration, dict) else None
if (
    raw.get("environment") != "development"
    or not isinstance(declared, str)
    or declared != hashlib.sha256(canonical).hexdigest()
    or not isinstance(migration, dict)
    or migration.get("enabled") is not True
    or not isinstance(allowed, list)
    or not allowed
    or not all(isinstance(uid, str) and uid.strip() for uid in allowed)
    or migration.get("maxConcurrency") != 1
    or not isinstance(migration.get("soakSeconds"), int)
    or migration["soakSeconds"] < 60
):
    raise SystemExit("migration manifest is not a canonical explicit development plan")
print(declared)
PY
} )"

manifest_uri="gs://${bucket}/agent-vm/migrations/${manifest_sha}.json"
active_uri="gs://${bucket}/agent-vm/releases/active.json"
previous_uri="gs://${bucket}/agent-vm/releases/previous.json"
gcloud storage cp --no-clobber "$manifest" "$manifest_uri"
readback="$(mktemp)"
trap 'rm -f "$readback"' EXIT
gcloud storage cp "$manifest_uri" "$readback"
cmp -s "$manifest" "$readback"

pointer_error="$(mktemp)"
trap 'rm -f "$readback" "$pointer_error"' EXIT
if active_generation="$(gcloud storage objects describe "$active_uri" --format='value(generation)' 2>"$pointer_error")"; then
  [[ "$active_generation" =~ ^[0-9]+$ ]]
elif grep -Eq '(^|[^-0-9])404([^0-9]|$)|NOT_FOUND' "$pointer_error"; then
  active_generation=0
else
  cat "$pointer_error" >&2
  echo "ERROR: active Agent VM manifest pointer could not be read; refusing activation." >&2
  exit 1
fi

# Snapshot the observed active generation into previous.json with its own
# compare-and-swap before changing the active pointer, so rollback can
# reliably return to the release that preceded this migration.
if [[ "$active_generation" != "0" ]]; then
  if previous_generation="$(gcloud storage objects describe "$previous_uri" --format='value(generation)' 2>/dev/null)"; then
    [[ "$previous_generation" =~ ^[0-9]+$ ]]
  else
    previous_generation=0
  fi
  gcloud storage cp "${active_uri}#${active_generation}" "$previous_uri" --if-generation-match="$previous_generation"
fi

gcloud storage cp "$manifest_uri" "$active_uri" --if-generation-match="$active_generation"
activated_generation="$(gcloud storage objects describe "$active_uri" --format='value(generation)')"
[[ "$activated_generation" =~ ^[0-9]+$ ]]
gcloud storage cp "${active_uri}#${activated_generation}" "$readback"
cmp -s "$manifest" "$readback"
echo "Activated development Agent VM migration manifest ${manifest_sha} at generation ${activated_generation}."
