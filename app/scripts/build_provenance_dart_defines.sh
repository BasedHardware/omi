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
  # The caller historically used this script inside command substitution:
  #   flutter build ... $(scripts/build_provenance_dart_defines.sh)
  # Bash does not propagate the substitution's exit status to that outer
  # command.  Emit an option that Flutter must reject as well as returning
  # non-zero, so a failed helper cannot silently run a build without the
  # provenance defines.  The marker contains no user-controlled data.
  printf '%s\n' '--__omi_build_provenance_failure__'
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

if [[ -n "${CM_COMMIT:-}" ]]; then
  [[ "$CM_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "invalid CM_COMMIT='$CM_COMMIT' (want 40 lowercase hex characters)"
  [[ "$sha" == "$CM_COMMIT" ]] || die "CM_COMMIT does not match checked-out HEAD ($sha)"
fi
if [[ -n "${OMI_RELEASE_SOURCE_SHA:-}" ]]; then
  [[ "$OMI_RELEASE_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || die "invalid OMI_RELEASE_SOURCE_SHA (want 40 lowercase hex characters)"
  [[ "$sha" == "$OMI_RELEASE_SOURCE_SHA" ]] || die "OMI_RELEASE_SOURCE_SHA does not match checked-out HEAD ($sha)"
fi

build="${BUILD_NUMBER:-${OMI_BUILD_NUMBER:-}}"
tag_build=""
if [[ -n "${CM_TAG:-}" ]]; then
  # Mobile tags are strict identity inputs.  Do not let a malformed or
  # platform-mismatched tag fall through to the old generic +N extraction.
  if [[ "$CM_TAG" == *-mobile-cm || "$CM_TAG" == *-ios-cm || "$CM_TAG" == *-android-cm ]]; then
    mobile_tag_re='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\+([1-9][0-9]{0,9})-(mobile|ios|android)-cm$'
    [[ "$CM_TAG" =~ $mobile_tag_re ]] || die "invalid mobile release tag '$CM_TAG'"
    tag_version="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.${BASH_REMATCH[3]}"
    tag_build="${BASH_REMATCH[4]}"
    tag_platform="${BASH_REMATCH[5]}"
    (( tag_build <= 2100000000 )) || die "mobile release build number exceeds 2100000000"

    if [[ -n "${OMI_RELEASE_PLATFORM:-}" ]]; then
      [[ "$OMI_RELEASE_PLATFORM" == ios || "$OMI_RELEASE_PLATFORM" == android ]] \
        || die "invalid OMI_RELEASE_PLATFORM='$OMI_RELEASE_PLATFORM'"
      [[ "$tag_platform" == mobile || "$tag_platform" == "$OMI_RELEASE_PLATFORM" ]] \
        || die "mobile tag platform '$tag_platform' does not match '$OMI_RELEASE_PLATFORM'"
    fi
    if [[ -n "${BUILD_NAME:-}" && "$BUILD_NAME" != "$tag_version" ]]; then
      die "BUILD_NAME='$BUILD_NAME' does not match mobile tag version '$tag_version'"
    fi
    if [[ -n "${OMI_RELEASE_VERSION:-}" && "$OMI_RELEASE_VERSION" != "$tag_version" ]]; then
      die "OMI_RELEASE_VERSION does not match mobile tag version '$tag_version'"
    fi
    if [[ -n "${BUILD_NUMBER:-}" && -n "${OMI_BUILD_NUMBER:-}" && "$BUILD_NUMBER" != "$OMI_BUILD_NUMBER" ]]; then
      die "BUILD_NUMBER and OMI_BUILD_NUMBER disagree"
    fi
    if [[ -n "$build" && "$build" != "$tag_build" ]]; then
      die "build number '$build' does not match mobile tag build '$tag_build'"
    fi
    build="$tag_build"
  elif [[ -z "$build" ]]; then
    # Preserve the generic +N extraction used by existing non-mobile release
    # callers (notably desktop) without weakening the mobile contract above.
    build="$(printf '%s' "$CM_TAG" | sed -n 's/^v[^+]*+\([0-9][0-9]*\).*/\1/p')"
  fi
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
