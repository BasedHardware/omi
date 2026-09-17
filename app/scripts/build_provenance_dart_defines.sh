#!/usr/bin/env bash
# Emit --dart-define flags that bake git SHA + build number into the Flutter
# binary. Run from app/ (Codemagic working_directory: app) or via an absolute
# path from setup.sh. Values are validated against a no-whitespace pattern
# before printing so unquoted $(...) word-splitting cannot inject extra args.
#
# BUILD_NUMBER: Codemagic env (already resolved from stores / CM_TAG), else
# OMI_BUILD_NUMBER, else the numeric +N from CM_TAG, else "local".
#
# Dirty means a *tracked* file differs from HEAD (worktree or index).
# Untracked and gitignored files do not count — Codemagic writes env, Firebase
# config, and keystore files that are gitignored or untracked.
set -euo pipefail

die() {
  echo "build provenance: $*" >&2
  exit 1
}

sha="unknown"
dirty="false"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$repo_root" ]]; then
  sha="$(git -C "$repo_root" rev-parse HEAD)"
  # Includes staged and unstaged changes to tracked files; ignores untracked.
  if ! git -C "$repo_root" diff --quiet HEAD --; then
    dirty="true"
    if [[ -n "${CM_BUILD_ID:-}" ]]; then
      echo "build provenance: tracked files differ from HEAD:" >&2
      git -C "$repo_root" diff --name-only HEAD -- >&2
    fi
  fi
fi

build="${BUILD_NUMBER:-${OMI_BUILD_NUMBER:-}}"
if [[ -z "$build" && -n "${CM_TAG:-}" ]]; then
  build="$(printf '%s' "$CM_TAG" | sed -n 's/^v[^+]*+\([0-9][0-9]*\).*/\1/p')"
fi
if [[ -z "$build" ]]; then
  build="local"
fi

[[ "$sha" =~ ^(unknown|[0-9a-f]{40})$ ]] || die "invalid OMI_GIT_SHA='$sha' (want 40 hex or unknown)"
[[ "$dirty" =~ ^(true|false)$ ]] || die "invalid OMI_GIT_DIRTY='$dirty'"
[[ "$build" =~ ^(local|[0-9]+)$ ]] || die "invalid OMI_BUILD_NUMBER='$build' (want digits or local)"

printf '%s\n' \
  "--dart-define=OMI_GIT_SHA=$sha" \
  "--dart-define=OMI_GIT_DIRTY=$dirty" \
  "--dart-define=OMI_BUILD_NUMBER=$build"
