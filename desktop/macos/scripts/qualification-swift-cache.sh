#!/usr/bin/env bash
# Prepare a stable, exact-source qualification checkout outside the Actions
# checkout. SwiftPM builds directly in that checkout's .build directory, so both
# source and output absolute paths remain identical across trusted retries.
set -euo pipefail
umask 077

usage() {
  cat <<'USAGE'
Usage: qualification-swift-cache.sh prepare <40-char-source-sha> <source-repository>

Prints the persistent exact-SHA source path on stdout. Diagnostics go to stderr.

Environment (test overrides are intentionally explicit):
  OMI_QUALIFICATION_SWIFT_CACHE_ROOT   Root (default: ~/Library/Caches/OmiDesktop/qualification-swiftpm-v2)
  OMI_QUALIFICATION_SWIFT_CACHE_XCODE  xcodebuild -version override
  OMI_QUALIFICATION_SWIFT_CACHE_SWIFT  xcrun swift --version override
  OMI_QUALIFICATION_SWIFT_CACHE_MACOS  sw_vers identity override
  OMI_QUALIFICATION_SWIFT_CACHE_ARCH   uname -m override
USAGE
}

[[ $# -eq 3 && "$1" == "prepare" ]] || { usage >&2; exit 2; }
SOURCE_SHA="$2"
SOURCE_REPOSITORY="$3"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo "qualification Swift cache: invalid source SHA: $SOURCE_SHA" >&2
  exit 2
}
git -C "$SOURCE_REPOSITORY" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "qualification Swift cache: source repository is not Git: $SOURCE_REPOSITORY" >&2
  exit 1
}

CACHE_ROOT="${OMI_QUALIFICATION_SWIFT_CACHE_ROOT:-$HOME/Library/Caches/OmiDesktop/qualification-swiftpm-v2}"
CACHE_DIR="$CACHE_ROOT/$SOURCE_SHA"
PERSISTENT_SOURCE="$CACHE_DIR/source"
PACKAGE_DIR="$PERSISTENT_SOURCE/desktop/macos/Desktop"
PACKAGE_SWIFT="$PACKAGE_DIR/Package.swift"
PACKAGE_RESOLVED="$PACKAGE_DIR/Package.resolved"
CACHE_BUILD="$PACKAGE_DIR/.build"
MANIFEST="$CACHE_DIR/manifest.json"
COMPLETE="$CACHE_DIR/complete"
XCODE="${OMI_QUALIFICATION_SWIFT_CACHE_XCODE:-$(xcodebuild -version 2>&1)}"
SWIFT="${OMI_QUALIFICATION_SWIFT_CACHE_SWIFT:-$(xcrun swift --version 2>&1)}"
MACOS="${OMI_QUALIFICATION_SWIFT_CACHE_MACOS:-$(printf '%s (%s)' "$(sw_vers -productVersion)" "$(sw_vers -buildVersion)")}"
ARCH="${OMI_QUALIFICATION_SWIFT_CACHE_ARCH:-$(uname -m)}"
TEMP_DIR=""
LOCK_DIR=""
LOCK_HELD=0

cleanup() {
  if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
    rm -rf "$TEMP_DIR"
  fi
  if [[ "$LOCK_HELD" -eq 1 && -n "$LOCK_DIR" && -d "$LOCK_DIR" && ! -L "$LOCK_DIR" ]]; then
    rm -rf "$LOCK_DIR"
  fi
}
trap cleanup EXIT

symlinked_component="$(python3 - "$CACHE_ROOT" <<'PY'
import os
import sys

path = os.path.abspath(os.path.expanduser(sys.argv[1]))
current = os.path.sep
for component in path.split(os.path.sep)[1:]:
    current = os.path.join(current, component)
    if os.path.lexists(current) and os.path.islink(current):
        print(current)
        raise SystemExit(0)
raise SystemExit(1)
PY
)" && {
  echo "qualification Swift cache: refusing symlinked cache path component: $symlinked_component" >&2
  exit 1
}
if [[ -e "$CACHE_ROOT" && ! -d "$CACHE_ROOT" ]]; then
  echo "qualification Swift cache: cache root collision: $CACHE_ROOT" >&2
  exit 1
fi
mkdir -p "$CACHE_ROOT"
chmod 700 "$CACHE_ROOT"

# Recheck after creation, then serialize all validation, cleanup, and publication
# for this exact SHA. mkdir is the atomic lock acquisition primitive on macOS.
symlinked_component="$(python3 - "$CACHE_ROOT" <<'PY'
import os
import sys

path = os.path.abspath(os.path.expanduser(sys.argv[1]))
current = os.path.sep
for component in path.split(os.path.sep)[1:]:
    current = os.path.join(current, component)
    if os.path.lexists(current) and os.path.islink(current):
        print(current)
        raise SystemExit(0)
raise SystemExit(1)
PY
)" && {
  echo "qualification Swift cache: refusing symlinked cache path component: $symlinked_component" >&2
  exit 1
}
LOCK_DIR="$CACHE_ROOT/.${SOURCE_SHA}.lock"
for _ in {1..1200}; do
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    LOCK_HELD=1
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    break
  fi
  # mkdir failed: either another prepare legitimately holds the lock (a
  # directory) or a non-directory squats the path. Read the type with a single
  # lstat. The previous check evaluated `-e` and `-d` as two separate stats, so
  # a concurrent holder releasing the lock (rm -rf) between them left `-e` true
  # and `-d` false and was misreported as a collision — the source of the
  # intermittent "lock destination collision" failures. A symlink or regular
  # file is a real, persistent squat and stays fatal; a vanished directory is
  # transient and simply retried.
  lock_type="$(stat -f '%HT' "$LOCK_DIR" 2>/dev/null || true)"
  if [[ -n "$lock_type" && "$lock_type" != "Directory" ]]; then
    echo "qualification Swift cache: lock destination collision (${lock_type}): $LOCK_DIR" >&2
    exit 1
  fi
  sleep 0.05
done
if [[ "$LOCK_HELD" -ne 1 ]]; then
  echo "qualification Swift cache: timed out waiting for exact-SHA cache lock: $LOCK_DIR" >&2
  exit 1
fi

if [[ -L "$CACHE_DIR" ]]; then
  echo "qualification Swift cache: refusing symlinked exact-SHA cache entry: $CACHE_DIR" >&2
  exit 1
fi
if [[ -e "$CACHE_DIR" && ! -d "$CACHE_DIR" ]]; then
  echo "qualification Swift cache: exact-SHA cache destination collision: $CACHE_DIR" >&2
  exit 1
fi

CACHE_STATE="HIT"
if [[ ! -e "$CACHE_DIR" ]]; then
  CACHE_STATE="MISS"
  TEMP_DIR="$(mktemp -d "$CACHE_ROOT/.${SOURCE_SHA}.prepare.XXXXXX")"
  mkdir "$TEMP_DIR/source"
  git clone --quiet --no-hardlinks --no-checkout "$SOURCE_REPOSITORY" "$TEMP_DIR/source"
  git -C "$TEMP_DIR/source" checkout --quiet --detach "$SOURCE_SHA"
  [[ "$(git -C "$TEMP_DIR/source" rev-parse HEAD)" == "$SOURCE_SHA" ]] || {
    echo "qualification Swift cache: cloned source SHA does not match candidate $SOURCE_SHA" >&2
    exit 1
  }
  mkdir -p "$TEMP_DIR/source/desktop/macos/Desktop/.build"
  CACHE_DIR="$TEMP_DIR"
  PERSISTENT_SOURCE="$CACHE_DIR/source"
  PACKAGE_DIR="$PERSISTENT_SOURCE/desktop/macos/Desktop"
  PACKAGE_SWIFT="$PACKAGE_DIR/Package.swift"
  PACKAGE_RESOLVED="$PACKAGE_DIR/Package.resolved"
  CACHE_BUILD="$PACKAGE_DIR/.build"
  MANIFEST="$CACHE_DIR/manifest.json"
  COMPLETE="$CACHE_DIR/complete"
fi

if [[ "$CACHE_STATE" == "HIT" ]]; then
  if [[ ! -f "$COMPLETE" || -L "$COMPLETE" || "$(cat "$COMPLETE" 2>/dev/null)" != "complete" \
        || ! -f "$MANIFEST" || -L "$MANIFEST" \
        || ! -d "$PERSISTENT_SOURCE" || -L "$PERSISTENT_SOURCE" \
        || ! -d "$CACHE_BUILD" || -L "$CACHE_BUILD" ]]; then
    echo "qualification Swift cache: incomplete exact-SHA cache entry: $CACHE_DIR" >&2
    exit 1
  fi
  [[ -d "$PERSISTENT_SOURCE/.git" && ! -L "$PERSISTENT_SOURCE/.git" ]] || {
    echo "qualification Swift cache: incomplete exact-SHA cache entry: $CACHE_DIR" >&2
    exit 1
  }
  WORKTREE_SHA="$(git -C "$PERSISTENT_SOURCE" rev-parse HEAD 2>/dev/null || true)"
  [[ "$WORKTREE_SHA" == "$SOURCE_SHA" ]] || {
    echo "qualification Swift cache: persistent source SHA $WORKTREE_SHA does not match candidate $SOURCE_SHA" >&2
    exit 1
  }
  if ! git -C "$PERSISTENT_SOURCE" diff --quiet --ignore-submodules -- \
      || ! git -C "$PERSISTENT_SOURCE" diff --cached --quiet --ignore-submodules --; then
    echo "qualification Swift cache: persistent source has tracked changes: $PERSISTENT_SOURCE" >&2
    exit 1
  fi
  # Remove all untrusted retry residue while preserving only SwiftPM's direct,
  # stable scratch directory. Tracked files are not rewritten, preserving mtimes.
  git -C "$PERSISTENT_SOURCE" clean -ffdx -e desktop/macos/Desktop/.build/ >/dev/null
fi

if [[ ! -f "$PACKAGE_SWIFT" || -L "$PACKAGE_SWIFT" \
      || ! -f "$PACKAGE_RESOLVED" || -L "$PACKAGE_RESOLVED" ]]; then
  echo "qualification Swift cache: package identity files are missing or symlinked" >&2
  exit 1
fi

EXPECTED_MANIFEST="$(python3 - "$SOURCE_SHA" "$PACKAGE_SWIFT" "$PACKAGE_RESOLVED" "$XCODE" "$SWIFT" "$MACOS" "$ARCH" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

source_sha, package_swift, package_resolved, xcode, swift, macos, arch = sys.argv[1:]

def digest(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

print(json.dumps({
    "cache_format": 2,
    "source_sha": source_sha,
    "package_swift_sha256": digest(package_swift),
    "package_resolved_sha256": digest(package_resolved),
    "xcode": xcode,
    "swift": swift,
    "macos": macos,
    "architecture": arch,
}, indent=2, sort_keys=True))
PY
)"

if [[ "$CACHE_STATE" == "HIT" ]]; then
  if ! python3 - "$MANIFEST" "$EXPECTED_MANIFEST" <<'PY'
import json
import sys
try:
    actual = json.load(open(sys.argv[1], encoding="utf-8"))
    expected = json.loads(sys.argv[2])
except (OSError, ValueError, TypeError):
    raise SystemExit(1)
raise SystemExit(0 if actual == expected else 1)
PY
  then
    echo "qualification Swift cache: cache provenance mismatch: $CACHE_DIR" >&2
    exit 1
  fi
else
  printf '%s\n' "$EXPECTED_MANIFEST" > "$MANIFEST"
  printf '%s\n' complete > "$COMPLETE"
  chmod 700 "$CACHE_DIR" "$PERSISTENT_SOURCE" "$CACHE_BUILD"
  FINAL_DIR="$CACHE_ROOT/$SOURCE_SHA"
  if [[ -e "$FINAL_DIR" || -L "$FINAL_DIR" ]] || ! mv "$CACHE_DIR" "$FINAL_DIR" 2>/dev/null; then
    echo "qualification Swift cache: exact-SHA cache destination collision: $FINAL_DIR" >&2
    exit 1
  fi
  TEMP_DIR=""
  CACHE_DIR="$FINAL_DIR"
  PERSISTENT_SOURCE="$CACHE_DIR/source"
fi

echo "qualification Swift cache $CACHE_STATE: source=$SOURCE_SHA path=$PERSISTENT_SOURCE" >&2
printf '%s\n' "$PERSISTENT_SOURCE"
