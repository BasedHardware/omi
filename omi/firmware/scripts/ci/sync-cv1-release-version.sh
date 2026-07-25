#!/usr/bin/env bash
#
# Preserve the reviewed image build number for a normal release. Only an
# explicit workflow version override starts a new base version at build zero.
#
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CONF=${1:?usage: sync-cv1-release-version.sh CONFIG [VERSION_OVERRIDE]}
VERSION_OVERRIDE=${2-}

if [[ $# -gt 2 ]]; then
  echo "usage: sync-cv1-release-version.sh CONFIG [VERSION_OVERRIDE]" >&2
  exit 1
fi

if [[ -n "$VERSION_OVERRIDE" ]]; then
  "$SCRIPT_DIR/set-cv1-version.sh" "$CONF" "${VERSION_OVERRIDE#v}"
else
  "$SCRIPT_DIR/check-cv1-version-sync.sh" "$CONF"
fi
