#!/bin/bash
set -euo pipefail

image="${AGENT_VM_IMAGE}"
release_id="${AGENT_VM_RELEASE_ID}"
image_digest="${AGENT_VM_IMAGE_DIGEST}"
backend_url="${AGENT_VM_BACKEND_URL}"
stop_audience="${AGENT_VM_STOP_AUDIENCE}"
startup_sha256="$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')"

metadata_get() {
  curl -fsS -H 'Metadata-Flavor: Google' "$1"
}

metadata_get_optional() {
  local response
  local status
  if ! response="$(curl -sS -H 'Metadata-Flavor: Google' -w $'\n%{http_code}' "$1")"; then
    return 2
  fi
  status="${response##*$'\n'}"
  response="${response%$'\n'*}"
  case "$status" in
    200)
      printf '%s' "$response"
      ;;
    404)
      return 1
      ;;
    *)
      return 2
      ;;
  esac
}

metadata_access_token() {
  metadata_get "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
}

secret_access() {
  local secret_name="$1"
  local project_id
  local access_token
  project_id="$(metadata_get 'http://metadata.google.internal/computeMetadata/v1/project/project-id')"
  access_token="$(metadata_access_token)"
  curl -fsS \
    -H "Authorization: Bearer $access_token" \
    "https://secretmanager.googleapis.com/v1/projects/${project_id}/secrets/${secret_name}/versions/latest:access" \
    | python3 -c 'import base64, json, sys; print(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode())'
}

state_fail() {
  echo "Agent VM durable state setup failed: $1" >&2
  exit 1
}

state_manifest() {
  local root="$1"
  local manifest="$2"
  local summary="$3"
  python3 - "$root" "$manifest" "$summary" <<'PY'
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
summary_path = Path(sys.argv[3])
entries = []
file_count = 0
total_bytes = 0

for current_root, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
    directory_names.sort()
    file_names.sort()
    current = Path(current_root)
    for name in directory_names + file_names:
        path = current / name
        relative = path.relative_to(root).as_posix()
        if relative == "state-receipt.json":
            continue
        mode = os.lstat(path).st_mode
        if stat.S_ISDIR(mode):
            entries.append({"path": relative, "type": "directory"})
        elif stat.S_ISREG(mode):
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
            entries.append({"bytes": size, "path": relative, "sha256": digest.hexdigest(), "type": "file"})
            file_count += 1
            total_bytes += size
        elif stat.S_ISLNK(mode):
            raise SystemExit(f"symlink is not allowed in durable state: {relative}")
        else:
            raise SystemExit(f"unsupported state entry type: {relative}")

manifest = b"".join(
    (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8") for entry in entries
)
manifest_path.write_bytes(manifest)
summary_path.write_text(
    json.dumps(
        {"digest": hashlib.sha256(manifest).hexdigest(), "count": file_count, "bytes": total_bytes},
        sort_keys=True,
        separators=(",", ":"),
    ),
    encoding="utf-8",
)
PY
}

state_receipt_is_valid() {
  local receipt="$1"
  python3 - "$receipt" <<'PY'
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    receipt = json.load(stream)
if not isinstance(receipt, dict) or receipt.get("schemaVersion") != 1:
    raise SystemExit(1)
if not isinstance(receipt.get("migrationId"), str) or not receipt["migrationId"]:
    raise SystemExit(1)
tree = receipt.get("tree")
db = receipt.get("db")
if not isinstance(tree, dict) or not isinstance(db, dict):
    raise SystemExit(1)
if not isinstance(tree.get("digest"), str) or re.fullmatch(r"[0-9a-f]{64}", tree["digest"]) is None:
    raise SystemExit(1)
if not isinstance(tree.get("count"), int) or isinstance(tree["count"], bool) or tree["count"] < 0:
    raise SystemExit(1)
if not isinstance(tree.get("bytes"), int) or isinstance(tree["bytes"], bool) or tree["bytes"] < 0:
    raise SystemExit(1)
if db.get("integrity") not in {"ok", "not_present"}:
    raise SystemExit(1)
print(db["integrity"], end="")
PY
}

state_write_receipt() {
  local receipt="$1"
  local migration_id="$2"
  local tree_digest="$3"
  local tree_count="$4"
  local tree_bytes="$5"
  local db_integrity="$6"
  python3 - "$receipt" "$migration_id" "$tree_digest" "$tree_count" "$tree_bytes" "$db_integrity" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

receipt_path = Path(sys.argv[1])
receipt_path.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "schemaVersion": 1,
    "migrationId": sys.argv[2],
    "tree": {"digest": sys.argv[3], "count": int(sys.argv[4]), "bytes": int(sys.argv[5])},
    "db": {"integrity": sys.argv[6]},
}
encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
fd, temporary_name = tempfile.mkstemp(prefix=".state-receipt.", dir=receipt_path.parent)
try:
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary_name, 0o644)
    os.replace(temporary_name, receipt_path)
finally:
    try:
        os.unlink(temporary_name)
    except FileNotFoundError:
        pass
PY
}

state_db_integrity() {
  local database="$1"
  if [[ ! -f "$database" ]]; then
    printf '%s' "not_present"
    return 0
  fi
  python3 - "$database" <<'PY'
import sqlite3
import sys

connection = None
try:
    connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    result = connection.execute("PRAGMA integrity_check").fetchall()
finally:
    if connection is not None:
        connection.close()
if result != [("ok",)]:
    raise SystemExit(1)
print("ok", end="")
PY
}

state_mount_source() {
  local device="$1"
  local mountpoint="$2"
  mkdir -p "$mountpoint"
  if mountpoint -q "$mountpoint"; then
    :
  else
    mount -o ro "$device" "$mountpoint" || state_fail "could not mount source read-only"
  fi
  local mounted_source
  local mount_options
  mounted_source="$(findmnt -n -o SOURCE --target "$mountpoint" 2>/dev/null || true)"
  mount_options="$(findmnt -n -o OPTIONS --target "$mountpoint" 2>/dev/null || true)"
  [[ -n "$mounted_source" ]] || state_fail "source mount was not visible"
  local expected_source actual_source
  expected_source="$(readlink -f "$device" 2>/dev/null || true)"
  actual_source="$(readlink -f "$mounted_source" 2>/dev/null || true)"
  [[ "$mounted_source" == "$device" || ( -n "$expected_source" && "$expected_source" == "$actual_source" ) ]] \
    || state_fail "source mount source mismatch"
  [[ ",$mount_options," == *,ro,* || "$mount_options" == ro* ]] || state_fail "source mount is not read-only"
}

state_mount_destination() {
  local device="$1"
  local mountpoint="$2"
  mkdir -p "$mountpoint"
  command -v blkid >/dev/null 2>&1 || state_fail "blkid is unavailable"
  command -v wipefs >/dev/null 2>&1 || state_fail "wipefs is unavailable"
  local filesystem_type
  filesystem_type="$(blkid -o value -s TYPE "$device" 2>/dev/null || true)"
  if [[ -z "$filesystem_type" ]]; then
    [[ -z "$(wipefs --noheadings "$device" 2>/dev/null || true)" ]] || state_fail "state device is not blank"
    mkfs.ext4 -F "$device" >/dev/null || state_fail "could not format blank state device"
  elif [[ "$filesystem_type" != "ext4" ]]; then
    state_fail "state device filesystem is not ext4"
  fi
  if mountpoint -q "$mountpoint"; then
    :
  else
    mount "$device" "$mountpoint" || state_fail "could not mount state device"
  fi
  local mounted_source
  mounted_source="$(findmnt -n -o SOURCE --target "$mountpoint" 2>/dev/null || true)"
  [[ -n "$mounted_source" ]] || state_fail "state mount was not visible"
  local expected_source actual_source
  expected_source="$(readlink -f "$device" 2>/dev/null || true)"
  actual_source="$(readlink -f "$mounted_source" 2>/dev/null || true)"
  [[ "$mounted_source" == "$device" || ( -n "$expected_source" && "$expected_source" == "$actual_source" ) ]] \
    || state_fail "state mount source mismatch"
}

ensure_state_tools() {
  local missing=false
  local tool
  for tool in mount findmnt blkid wipefs mkfs.ext4; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing=true
    fi
  done
  if [[ "$missing" == true ]]; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y util-linux e2fsprogs
  fi
  for tool in mount findmnt blkid wipefs mkfs.ext4; do
    command -v "$tool" >/dev/null 2>&1 || state_fail "$tool is unavailable after package bootstrap"
  done
}

state_required_raw=""
if state_required_raw="$(metadata_get_optional 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/omi-agent-state-required')"; then
  :
else
  state_required_status=$?
  [[ "$state_required_status" == 1 ]] || state_fail "state requirement metadata is unavailable"
fi
state_required="${state_required_raw//$'\r'/}"
state_required="${state_required//$'\n'/}"
case "${state_required,,}" in
  ""|false)
    state_required=false
    ;;
  true)
    state_required=true
    ;;
  *)
    state_fail "invalid omi-agent-state-required metadata"
    ;;
esac

data_dir="${AGENT_VM_DATA_DIR:-/var/lib/omi-agent}"
state_device="${AGENT_VM_STATE_DEVICE:-/dev/disk/by-id/google-omi-agent-state}"
state_source_device="${AGENT_VM_STATE_SOURCE_DEVICE:-/dev/disk/by-id/google-omi-agent-state-source-part1}"
state_mount="${AGENT_VM_STATE_MOUNT:-/var/lib/omi-agent}"
state_source_mount="${AGENT_VM_STATE_SOURCE_MOUNT:-/run/omi-agent-state-source}"
state_migration_id=""
state_receipt_name="state-receipt.json"
state_receipt="${state_mount}/${state_receipt_name}"

if [[ "$state_required" == true || -e "$state_device" ]]; then
  [[ -e "$state_device" ]] || state_fail "required state device is missing"
  state_migration_id="$(metadata_get 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/omi-agent-migration' 2>/dev/null || true)"
  if [[ -z "$state_migration_id" ]]; then
    state_migration_id="$(metadata_get 'http://metadata.google.internal/computeMetadata/v1/instance/name' 2>/dev/null || true)"
  fi
  [[ -n "$state_migration_id" ]] || state_fail "state migration metadata is missing"
  ensure_state_tools
  state_mount_destination "$state_device" "$state_mount"
  data_dir="$state_mount"
  if [[ -d "$data_dir/lost+found" ]]; then
    rmdir "$data_dir/lost+found" || state_fail "state disk is not empty"
  fi

  state_receipt_present=false
  state_previous_db_integrity=""
  if [[ -e "$state_receipt" ]]; then
    [[ -f "$state_receipt" && ! -L "$state_receipt" ]] || state_fail "state receipt is not a regular file"
    state_previous_db_integrity="$(state_receipt_is_valid "$state_receipt")" \
      || state_fail "state receipt schema mismatch"
    state_receipt_present=true
  fi

  if [[ "$state_receipt_present" == false && -e "$state_source_device" ]]; then
    state_mount_source "$state_source_device" "$state_source_mount"
    state_source_dir="$state_source_mount/var/lib/omi-agent"
    [[ -d "$state_source_dir" ]] || state_fail "legacy state directory is missing from source clone"
    # No receipt means no migration ever committed. A prior interrupted copy
    # may have left partial files; discard only this uncommitted destination
    # and reconstruct it from the still-read-only source clone.
    python3 - "$data_dir" <<'PY' || state_fail "could not reset an uncommitted state copy"
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
for path in root.iterdir():
    if path.name == "state-receipt.json":
        continue
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
PY
    state_staging_dir="$data_dir/.migration-staging"
    mkdir -p "$state_staging_dir"
    cp -a "$state_source_dir"/. "$state_staging_dir"/ || state_fail "could not copy legacy state"
    state_source_manifest="$(mktemp)"
    state_destination_manifest="$(mktemp)"
    state_source_summary="$(mktemp)"
    state_destination_summary="$(mktemp)"
    state_manifest "$state_source_dir" "$state_source_manifest" "$state_source_summary" || state_fail "could not inspect source state"
    state_manifest "$state_staging_dir" "$state_destination_manifest" "$state_destination_summary" || state_fail "could not inspect destination state"
    cmp -s "$state_source_manifest" "$state_destination_manifest" || state_fail "source and destination state differ"
    python3 - "$state_staging_dir" "$data_dir" <<'PY' || state_fail "could not commit migrated state"
import os
import sys
from pathlib import Path

staging = Path(sys.argv[1])
destination = Path(sys.argv[2])
for path in sorted(staging.iterdir(), key=lambda item: item.name):
    os.replace(path, destination / path.name)
staging.rmdir()
directory_fd = os.open(destination, os.O_RDONLY)
try:
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
PY
    umount "$state_source_mount" || state_fail "could not unmount source clone"
    rm -f "$state_source_manifest" "$state_destination_manifest" "$state_source_summary" "$state_destination_summary"
  elif [[ "$state_receipt_present" == false ]]; then
    python3 - "$data_dir" <<'PY' || state_fail "state disk is not empty"
import sys
from pathlib import Path

root = Path(sys.argv[1])
if any(path.name != "state-receipt.json" for path in root.iterdir()):
    raise SystemExit(1)
PY
  fi

  mkdir -p "$data_dir/data" "$data_dir/workspace"
  state_manifest_file="$(mktemp)"
  state_summary_file="$(mktemp)"
  state_manifest "$data_dir" "$state_manifest_file" "$state_summary_file" || state_fail "could not inspect state"
  state_tree_values="$(python3 - "$state_summary_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    summary = json.load(stream)
print(summary["digest"])
print(summary["count"])
print(summary["bytes"])
PY
)"
  mapfile -t state_tree <<<"$state_tree_values"
  [[ "${#state_tree[@]}" == 3 ]] || state_fail "invalid state tree summary"
  state_db_integrity_value="$(state_db_integrity "$data_dir/data/omi.db")" || state_fail "state database integrity check failed"
  if [[ "$state_previous_db_integrity" == ok && "$state_db_integrity_value" != ok ]]; then
    state_fail "previously durable state database is missing"
  fi
  state_write_receipt "$state_receipt" "$state_migration_id" "${state_tree[0]}" "${state_tree[1]}" "${state_tree[2]}" "$state_db_integrity_value" \
    || state_fail "could not write state receipt"
  rm -f "$state_manifest_file" "$state_summary_file"
else
  mkdir -p "$data_dir/data" "$data_dir/workspace"
fi

auth_token="$(metadata_get 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/auth-token')"
anthropic_api_key="$(secret_access DESKTOP_ANTHROPIC_API_KEY)"
gemini_secret_name="${AGENT_VM_GEMINI_SECRET_NAME}"
gemini_api_key="$(secret_access "$gemini_secret_name")"
mkdir -p "$data_dir"

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io
fi
if ! docker info >/dev/null 2>&1; then
  if command -v systemctl >/dev/null 2>&1 && systemctl enable --now docker; then
    :
  elif command -v service >/dev/null 2>&1; then
    service docker start
  else
    echo 'Docker daemon could not be started' >&2
    exit 1
  fi
fi

# Agent VM base images before the immutable-container rollout boot a legacy
# host-level Node service on port 8080. Retire only that known service before
# taking over the listener with the release-pinned container below. The guard
# keeps fresh images (which have no legacy unit) idempotent.
if systemctl cat omi-agent.service >/dev/null 2>&1; then
  systemctl disable --now omi-agent.service || true
fi

registry_token="$(metadata_access_token)"
printf '%s' "$registry_token" | docker login --username oauth2accesstoken --password-stdin https://gcr.io >/dev/null
docker pull "$image"
if docker container inspect omi-agent-vm >/dev/null 2>&1; then
  docker rm -f omi-agent-vm >/dev/null
fi
backend_env=()
if [[ -n "$backend_url" ]]; then
  backend_env=(--env "BACKEND_URL=$backend_url")
fi
docker run --detach --name omi-agent-vm --restart unless-stopped --publish 8080:8080 \
  --env ANTHROPIC_API_KEY="$anthropic_api_key" --env AUTH_TOKEN="$auth_token" --env GEMINI_API_KEY="$gemini_api_key" \
  --env AGENT_VM_RELEASE_ID="$release_id" --env AGENT_VM_IMAGE_DIGEST="$image_digest" \
  --env AGENT_VM_STARTUP_SHA256="$startup_sha256" "${backend_env[@]}" \
  --env AGENT_VM_STOP_AUDIENCE="$stop_audience" \
  --env DB_PATH=/root/omi-agent/data/omi.db --env AGENT_VM_WORKSPACE=/root/omi-agent/workspace \
  --env STATE_RECEIPT_PATH=/root/omi-agent/state-receipt.json --env AGENT_VM_STATE_MIGRATION_ID="$state_migration_id" \
  --env PLAYWRIGHT_MCP_COMMAND=playwright-mcp \
  --env PLAYWRIGHT_MCP_ARGS='["--user-data-dir", "/app/chrome-profile", "--headless", "--no-sandbox"]' \
  --tmpfs /app/chrome-profile:rw,exec \
  --volume "$data_dir:/root/omi-agent" "$image"
