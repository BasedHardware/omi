#!/usr/bin/env bash
# Warn when pushing continuity-sensitive branches whose HEAD lacks green gauntlet evidence.
#
# Usage:
#   ./scripts/check-gauntlet-evidence-at-head.sh          # warn (default)
#   ./scripts/check-gauntlet-evidence-at-head.sh block    # exit 1 when missing
#
# Looks for desktop/macos/.harness/agent-continuity-gauntlet/*/manifest.json with
# matching git SHA and passed: true.
#
# Applies to branches matching:
#   desktop-agent-* | *continuity* | *chat-timeline* | *floating-viewport*
#   | *kernel-turn* | *agent-pill* | *floating-chat*
# (INV-6 Continuity PR DoD — live suite is a PR/RC gate, not CI.)

set -euo pipefail

MODE="${1:-warn}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"
HARNESS_ROOT="$DESKTOP_DIR/.harness/agent-continuity-gauntlet"

cd "$REPO_ROOT"
HEAD_SHA="$(git rev-parse --short HEAD)"
BRANCH="$(git symbolic-ref --short -q HEAD 2>/dev/null || true)"

if [[ ! "$BRANCH" =~ (^desktop-agent-|continuity|chat-timeline|floating-viewport|kernel-turn|agent-pill|floating-chat) ]]; then
  exit 0
fi

if [[ ! -d "$HARNESS_ROOT" ]]; then
  echo "WARN: branch $BRANCH at $HEAD_SHA has no gauntlet evidence directory ($HARNESS_ROOT)." >&2
  echo "WARN: run: cd desktop/macos && ./scripts/agent-continuity-gauntlet.sh" >&2
  if [[ "$MODE" == "block" ]]; then
    exit 1
  fi
  exit 0
fi

FOUND=false
for manifest in "$HARNESS_ROOT"/*/manifest.json; do
  [[ -f "$manifest" ]] || continue
  if python3 - "$manifest" "$HEAD_SHA" <<'PY'
import json
import sys

manifest_path, head_sha = sys.argv[1], sys.argv[2]
with open(manifest_path, encoding="utf-8") as handle:
    data = json.load(handle)
if data.get("git") == head_sha and data.get("passed") is True:
    raise SystemExit(0)
raise SystemExit(1)
PY
  then
    FOUND=true
    break
  fi
done

if [[ "$FOUND" != true ]]; then
  echo "WARN: pushing $BRANCH at $HEAD_SHA with no green gauntlet bundle at HEAD." >&2
  echo "WARN: run: cd desktop/macos && OMI_APP_NAME=omi-gauntlet ./scripts/agent-continuity-gauntlet.sh" >&2
  if [[ "$MODE" == "block" ]]; then
    exit 1
  fi
fi
