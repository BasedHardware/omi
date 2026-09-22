#!/usr/bin/env bash
# Bless a Python backend SHA by running required checks and publishing evidence.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$BACKEND_DIR/.." && pwd)"

TARGET_REF="HEAD"
REPO="BasedHardware/omi"
KEEP_EVIDENCE=0

usage() {
  cat <<'USAGE'
Bless a Python backend SHA (tests + workflow contracts + OpenAPI evidence).

Usage:
  backend/scripts/bless-python-backend.sh [--ref <git-ref>] [--repo owner/name] [--keep-evidence]

The script creates or updates GitHub Release python-backend-bless-<full-sha> and
uploads python-backend-bless-evidence-<short-sha>-<timestamp>.json.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      if [[ $# -lt 2 || "${2:-}" == -* ]]; then
        echo "--ref requires a git ref value" >&2
        usage >&2
        exit 2
      fi
      TARGET_REF="${2:-}"
      shift 2
      ;;
    --repo)
      if [[ $# -lt 2 || "${2:-}" == -* ]]; then
        echo "--repo requires an owner/name value" >&2
        usage >&2
        exit 2
      fi
      REPO="${2:-}"
      shift 2
      ;;
    --keep-evidence)
      KEEP_EVIDENCE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      echo "unexpected argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$TARGET_REF" || -z "$REPO" ]]; then
  usage >&2
  exit 2
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "bless-python-backend.sh requires gh CLI" >&2
  exit 1
fi

TARGET_SHA="$(git -C "$REPO_ROOT" rev-parse "$TARGET_REF^{commit}")"
CURRENT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
if [[ "$CURRENT_SHA" != "$TARGET_SHA" ]]; then
  echo "ref $TARGET_REF resolves to $TARGET_SHA, but this checkout is at $CURRENT_SHA" >&2
  echo "Check out the target commit before blessing so evidence is collected from the blessed source." >&2
  exit 1
fi
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no)" ]]; then
  echo "worktree has tracked changes; refusing to bless dirty source" >&2
  git -C "$REPO_ROOT" status --short --untracked-files=no >&2
  exit 1
fi
SHORT_SHA="${TARGET_SHA:0:12}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ISO_STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BLESS_TAG="python-backend-bless-${TARGET_SHA}"
EVIDENCE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/python-backend-bless.XXXXXX")"
EVIDENCE_FILE="$EVIDENCE_DIR/python-backend-bless-evidence-${SHORT_SHA}-${STAMP}.json"
BODY_FILE="$EVIDENCE_DIR/release-body.md"
COMMANDS_FILE="$EVIDENCE_DIR/commands.jsonl"

cleanup() {
  if [[ "$KEEP_EVIDENCE" -eq 0 ]]; then
    rm -rf "$EVIDENCE_DIR"
  else
    echo "kept evidence directory: $EVIDENCE_DIR"
  fi
}
trap cleanup EXIT

run_evidence_command() {
  local name="$1"
  shift
  local log_file="$EVIDENCE_DIR/${name}.log"
  local started_at ended_at status
  started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "running $name: $*"
  set +e
  (cd "$BACKEND_DIR" && "$@") >"$log_file" 2>&1
  status=$?
  set -e
  ended_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 - "$COMMANDS_FILE" "$name" "$started_at" "$ended_at" "$status" "$log_file" "$@" <<'PY'
import json
import sys

path, name, started_at, ended_at, status, log_file, *command = sys.argv[1:]
with open(path, "a", encoding="utf-8") as f:
    f.write(
        json.dumps(
            {
                "name": name,
                "command": command,
                "started_at": started_at,
                "ended_at": ended_at,
                "exit_code": int(status),
                "log": log_file,
            },
            sort_keys=True,
        )
        + "\n"
    )
PY
  if [[ "$status" -ne 0 ]]; then
    echo "$name failed; see $log_file" >&2
    tail -80 "$log_file" >&2 || true
    return "$status"
  fi
}

run_evidence_command test-preflight bash test-preflight.sh
run_evidence_command backend-test bash test.sh
run_evidence_command workflow-contracts python3 scripts/check_workflow_contracts.py
run_evidence_command openapi-public scripts/openapi_runner.sh scripts/export_openapi.py --check ../docs/api-reference/openapi.json
run_evidence_command openapi-app-client scripts/openapi_runner.sh scripts/export_openapi.py --surface app-client --check ../docs/api-reference/app-client-openapi.json
run_evidence_command openapi-integration-public scripts/openapi_runner.sh scripts/export_openapi.py --surface integration-public --check ../docs/api-reference/integration-public-openapi.json

python3 - "$COMMANDS_FILE" "$EVIDENCE_FILE" "$TARGET_SHA" "$ISO_STAMP" <<'PY'
import json
import sys

commands_path, evidence_path, target_sha, blessed_at = sys.argv[1:]
commands = [json.loads(line) for line in open(commands_path, encoding="utf-8")]
evidence = {
    "surface": "python-backend",
    "sha": target_sha,
    "blessed_at": blessed_at,
    "tier": "unit+workflow-contracts+openapi",
    "passed": all(command["exit_code"] == 0 for command in commands),
    "commands": commands,
}
with open(evidence_path, "w", encoding="utf-8") as f:
    json.dump(evidence, f, indent=2, sort_keys=True)
    f.write("\n")
PY

cat >"$BODY_FILE" <<EOF
Python backend blessing for ${TARGET_SHA}

KEY_VALUE_START
surface: python-backend
blessed.python-backend: true
blessed.python-backend.at: ${ISO_STAMP}
blessed.python-backend.sha: ${TARGET_SHA}
blessed.python-backend.tier: unit+workflow-contracts+openapi
blessed.python-backend.evidence: $(basename "$EVIDENCE_FILE")
KEY_VALUE_END
EOF

if gh release view "$BLESS_TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release edit "$BLESS_TAG" --repo "$REPO" --notes-file "$BODY_FILE" --title "Python backend blessing ${SHORT_SHA}"
else
  gh release create "$BLESS_TAG" "$EVIDENCE_FILE" \
    --repo "$REPO" \
    --target "$TARGET_SHA" \
    --title "Python backend blessing ${SHORT_SHA}" \
    --notes-file "$BODY_FILE" \
    --prerelease \
    --latest=false
fi

gh release upload "$BLESS_TAG" "$EVIDENCE_FILE" --repo "$REPO" --clobber
echo "blessed python-backend $TARGET_SHA with evidence $(basename "$EVIDENCE_FILE")"
