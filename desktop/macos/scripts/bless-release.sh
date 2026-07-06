#!/usr/bin/env bash
# Bless a macOS desktop beta release by rebuilding the tag and running T2 core E2E.
#
# Usage:
#   ./scripts/bless-release.sh v11.0.0+11000-macos
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"

RELEASE_TAG="${1:-}"
if [[ -z "$RELEASE_TAG" ]]; then
  echo "usage: bless-release.sh <vX.Y.Z+BUILD-macos>" >&2
  exit 2
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "bless-release.sh requires macOS" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "bless-release.sh requires gh CLI" >&2
  exit 1
fi

VERSION="${RELEASE_TAG#v}"
VERSION="${VERSION%-macos}"
BUNDLE="omi-bless-${VERSION}"
WORKTREE="$REPO_ROOT/.bless-worktrees/$RELEASE_TAG"

gh release view "$RELEASE_TAG" --repo BasedHardware/omi --json tagName,isDraft,isPrerelease,body \
  > /tmp/bless-release.json

python3 - /tmp/bless-release.json "$RELEASE_TAG" <<'PY'
import json
import re
import sys

release = json.loads(open(sys.argv[1], encoding="utf-8").read())
tag = sys.argv[2]
if release.get("tagName") != tag:
    raise SystemExit(f"tag mismatch: {release.get('tagName')}")
if release.get("isDraft") or release.get("isPrerelease"):
    raise SystemExit("release must be published and not a GitHub prerelease")

body = release.get("body") or ""
metadata = {}
in_block = False
for line in body.splitlines():
    stripped = line.strip().removeprefix("<!--").removesuffix("-->").strip()
    if stripped == "KEY_VALUE_START":
        in_block = True
        continue
    if stripped == "KEY_VALUE_END":
        break
    if in_block and ":" in stripped:
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip()

if metadata.get("channel") != "beta":
    raise SystemExit(f"channel must be beta, got {metadata.get('channel')!r}")
is_live = metadata.get("isLive", "").lower()
if is_live not in {"true", "1", "yes"}:
    raise SystemExit(f"isLive must be true, got {metadata.get('isLive')!r}")
if not re.match(r"^v\d+\.\d+(?:\.\d+)?\+\d+-macos$", tag):
    raise SystemExit(f"not a macOS release tag: {tag}")
print("release preflight OK")
PY

SHA=$(git -C "$REPO_ROOT" rev-list -n1 "$RELEASE_TAG")

rm -rf "$WORKTREE"
git -C "$REPO_ROOT" worktree add --detach "$WORKTREE" "$RELEASE_TAG"

(
  cd "$WORKTREE/desktop/macos"
  PROVIDER_MODE=offline make -C "$WORKTREE" dev-up
  OMI_APP_NAME="$BUNDLE" OMI_SKIP_TUNNEL=1 ./run.sh
  ./scripts/omi-auth-seed.sh "com.omi.$BUNDLE" || true
  ./scripts/desktop-core-harness.sh --tier 2 --bundle "$BUNDLE" --keep-stack
)

EVIDENCE=$(ls -td "$WORKTREE/desktop/macos/.harness/desktop-core"/* 2>/dev/null | head -1)
if [[ -z "$EVIDENCE" || ! -f "$EVIDENCE/manifest.json" ]]; then
  echo "bless failed: missing harness evidence" >&2
  exit 1
fi

if ! python3 - "$EVIDENCE/manifest.json" <<'PY'
import json, sys
manifest = json.loads(open(sys.argv[1]).read())
raise SystemExit(1) if not manifest.get("passed") else None
PY
then
  echo "bless failed: tier 2 harness did not pass; evidence: $EVIDENCE" >&2
  exit 1
fi

STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ASSET="bless-evidence-${VERSION}-$(date -u +%Y%m%dT%H%M%SZ).json"
cp "$EVIDENCE/manifest.json" "/tmp/$ASSET"

BODY_FILE=/tmp/bless-release-body.md
gh release view "$RELEASE_TAG" --repo BasedHardware/omi --json body --jq .body > "$BODY_FILE"

python3 - "$BODY_FILE" "$STAMP" "$SHA" "$ASSET" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
stamp, sha, asset = sys.argv[2:5]
lines = path.read_text(encoding="utf-8").splitlines()
out = []
in_block = False
seen = {key: False for key in ("blessed", "blessedAt", "blessedSha", "blessedTier", "blessedEvidence")}

for line in lines:
    stripped = line.strip().removeprefix("<!--").removesuffix("-->").strip()
    if stripped == "KEY_VALUE_START":
        in_block = True
        out.append(line)
        continue
    if stripped == "KEY_VALUE_END":
        for key, value in (
            ("blessed", "true"),
            ("blessedAt", stamp),
            ("blessedSha", sha),
            ("blessedTier", "2"),
            ("blessedEvidence", asset),
        ):
            if not seen[key]:
                out.append(f"{key}: {value}")
        in_block = False
        out.append(line)
        continue
    if in_block and stripped.split(":", 1)[0].strip() in seen:
        key = stripped.split(":", 1)[0].strip()
        if key == "blessed":
            out.append("blessed: true")
        elif key == "blessedAt":
            out.append(f"blessedAt: {stamp}")
        elif key == "blessedSha":
            out.append(f"blessedSha: {sha}")
        elif key == "blessedTier":
            out.append("blessedTier: 2")
        elif key == "blessedEvidence":
            out.append(f"blessedEvidence: {asset}")
        seen[key] = True
        continue
    out.append(line)

path.write_text("\n".join(out) + ("\n" if path.read_text().endswith("\n") else ""), encoding="utf-8")
PY

gh release upload "$RELEASE_TAG" "/tmp/$ASSET" --repo BasedHardware/omi --clobber
gh release edit "$RELEASE_TAG" --repo BasedHardware/omi --notes-file "$BODY_FILE"

echo "Blessed $RELEASE_TAG at $SHA (evidence asset: $ASSET)"
