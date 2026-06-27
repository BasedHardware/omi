#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <bundle-dir> [source-commit] [source-branch]" >&2
  exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
BUNDLE_DIR=$1
SOURCE_COMMIT=${2:-local}
SOURCE_BRANCH=${3:-local}

TMP_DIR=$(mktemp -d)
ASSETS_DIR="$TMP_DIR/assets"
mkdir -p "$ASSETS_DIR"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

cd "$REPO_ROOT/desktop/Desktop"

# Put Apple-provided tools first so SwiftPM does not pick up a broken Homebrew git on CI/macOS hosts.
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:$PATH"

swift run -c debug "Omi Computer" --export-onboarding "$ASSETS_DIR"

"$SCRIPT_DIR/prepare_onboarding_sync_bundle.sh" "$ASSETS_DIR" "$BUNDLE_DIR" "$SOURCE_COMMIT" "$SOURCE_BRANCH"
