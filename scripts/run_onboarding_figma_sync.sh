#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SOURCE_REPO_DEFAULT=$(cd "$SCRIPT_DIR/.." && pwd)

SOURCE_REPO=${SOURCE_REPO:-$SOURCE_REPO_DEFAULT}
STATE_DIR=${STATE_DIR:-"$HOME/Library/Application Support/OMIOnboardingSync"}
EXPORT_REPO=${EXPORT_REPO:-"$STATE_DIR/export-worktree"}
SITE_DIR="$STATE_DIR/site"
LOG_FILE="$STATE_DIR/sync.log"
HTTP_LOG="$STATE_DIR/http.log"
RESULT_FILE="$STATE_DIR/last_result.txt"
LOCK_DIR="$STATE_DIR/run.lock"
PORT=${PORT:-8765}
CODEX_BIN=${CODEX_BIN:-$(command -v codex || true)}
NODE_BIN_DIR=${NODE_BIN_DIR:-$(command -v node >/dev/null 2>&1 && dirname "$(command -v node)" || true)}
export PATH="${NODE_BIN_DIR:+$NODE_BIN_DIR:}/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

mkdir -p "$STATE_DIR"

if [[ -z "$CODEX_BIN" || ! -x "$CODEX_BIN" ]]; then
  echo "codex binary not found; set CODEX_BIN or install codex" >&2
  exit 127
fi

if [[ ! -d "$EXPORT_REPO/.git" && ! -f "$EXPORT_REPO/.git" ]]; then
  echo "export worktree missing: $EXPORT_REPO" >&2
  exit 1
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi

cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

exec >>"$LOG_FILE" 2>&1

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] sync start"
sleep 2

FILES_TO_SYNC=$(mktemp)
trap 'rm -f "$FILES_TO_SYNC"; cleanup' EXIT

(
  cd "$SOURCE_REPO"
  find desktop/Desktop/Sources -type f \
    \( -name 'Onboarding*.swift' \
    -o -name 'PostOnboardingPromptViews.swift' \
    -o -path 'desktop/Desktop/Sources/FileIndexing/OnboardingLoadingAnimation.swift' \
    -o -path 'desktop/Desktop/Sources/FloatingControlBar/ShortcutSettings.swift' \
    -o -path 'desktop/Desktop/Sources/Theme/OmiColors.swift' \) \
    | sort
) >"$FILES_TO_SYNC"

rsync -a --files-from="$FILES_TO_SYNC" "$SOURCE_REPO/" "$EXPORT_REPO/"
python3 "$EXPORT_REPO/scripts/apply_export_preview_overrides.py" "$EXPORT_REPO/desktop/Desktop/Sources"

SOURCE_COMMIT=$(git -C "$SOURCE_REPO" rev-parse HEAD 2>/dev/null || echo local)
SOURCE_BRANCH=$(git -C "$SOURCE_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo local)
if [[ -n "$(git -C "$SOURCE_REPO" status --porcelain 2>/dev/null || true)" ]]; then
  SOURCE_BRANCH="${SOURCE_BRANCH}-dirty"
fi

"$EXPORT_REPO/scripts/export_onboarding_sync_bundle.sh" "$SITE_DIR" "$SOURCE_COMMIT" "$SOURCE_BRANCH"

if ! lsof -ti tcp:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  nohup python3 -m http.server "$PORT" --directory "$SITE_DIR" >"$HTTP_LOG" 2>&1 &
  sleep 2
fi

pkill -f 'chrome-devtools-mcp' || true
pkill -f '/Users/nik/.cache/chrome-devtools-mcp/chrome-profile' || true
pkill -f "codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C $SITE_DIR" || true
sleep 1

rm -f "$RESULT_FILE"

cat <<EOF | "$CODEX_BIN" exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C "$SITE_DIR" -o "$RESULT_FILE" -
Do not inspect local skill files.
Capture http://127.0.0.1:${PORT}/index.html into the existing Figma file https://www.figma.com/file/pK7sTlaBnVRwnBroajw0Qi/omi?node-id=2711-1688&type=design on the \`500k users\` page.
Delete any existing top-level \`OMI Onboarding Sync\` frame on that page first.
Important: if the code-to-canvas tool returns a pending capture, you must open the returned localhost capture URL so the page submits the capture, then continue polling until it completes.
After it lands, rename the resulting top-level frame to \`OMI Onboarding Sync\` and verify there is exactly one such top-level frame on \`500k users\`.
Respond with exactly one line: \`OK <node-id>\` or \`FAIL <reason>\`.
EOF

if [[ ! -f "$RESULT_FILE" ]]; then
  echo "FAIL no-result-file" >"$RESULT_FILE"
fi

RESULT_LINE=$(tr '\n' ' ' < "$RESULT_FILE")
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] sync done: $RESULT_LINE"
