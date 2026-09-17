#!/usr/bin/env bash
# Emit --dart-define flags that bake git SHA + build number into the Flutter
# binary. Values must not contain whitespace (word-split by Codemagic callers).
# BUILD_NUMBER: Codemagic env (already resolved from stores / CM_TAG), else
# OMI_BUILD_NUMBER, else the numeric part of CM_TAG, else "local".
set -euo pipefail

sha="unknown"
dirty="false"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$repo_root" ]]; then
  sha="$(git -C "$repo_root" rev-parse HEAD)"
  if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
    dirty="true"
  fi
fi

build="${BUILD_NUMBER:-${OMI_BUILD_NUMBER:-}}"
if [[ -z "$build" && -n "${CM_TAG:-}" ]]; then
  build="$(printf '%s' "$CM_TAG" | sed -n 's/^v[^+]*+\([0-9][0-9]*\).*/\1/p')"
fi
if [[ -z "$build" ]]; then
  build="local"
fi

printf '%s\n' \
  "--dart-define=OMI_GIT_SHA=$sha" \
  "--dart-define=OMI_GIT_DIRTY=$dirty" \
  "--dart-define=OMI_BUILD_NUMBER=$build"
