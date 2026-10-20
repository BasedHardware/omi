#!/usr/bin/env bash
# Make the Codemagic checkout the exact commit the dispatcher evaluated.
#
# .github/scripts/dispatch_mobile_internal_builds.py can only name a branch, plus the
# evaluated SHA in OMI_RELEASE_SOURCE_SHA. main can move in the minute between dispatch
# and clone; on 2026-10-20 both the iOS and Android internal builds failed the exact-HEAD
# check that way. When the cloned tip still contains the pin, build the pin itself.
# Anything else fails closed: an invalid pin, a pin the tip does not contain, or a pin
# that cannot be fetched or checked out.
#
# The body is one function so bash has parsed all of it before `git checkout` can
# replace this file on disk.
set -euo pipefail

main() {
  local pin="${OMI_RELEASE_SOURCE_SHA:-}"
  if [[ -z "$pin" ]]; then
    echo "no dispatcher source pin; building the branch tip"
    return 0
  fi
  if [[ ! "$pin" =~ ^[0-9a-f]{40}$ ]]; then
    echo "invalid OMI_RELEASE_SOURCE_SHA (want 40 lowercase hex characters)" >&2
    return 1
  fi

  local head
  head="$(git rev-parse HEAD)"
  if [[ "$head" == "$pin" ]]; then
    echo "checked-out HEAD matches dispatcher source pin $pin"
    return 0
  fi

  echo "branch tip $head moved past dispatcher source pin $pin"
  if ! git cat-file -e "${pin}^{commit}" 2>/dev/null; then
    git fetch --no-tags origin "$pin"
  fi
  if ! git merge-base --is-ancestor "$pin" "$head" 2>/dev/null \
    && [[ "$(git rev-parse --is-shallow-repository)" == "true" ]]; then
    git fetch --no-tags --unshallow origin
  fi
  if ! git merge-base --is-ancestor "$pin" "$head"; then
    echo "dispatcher source pin $pin is not contained in the checked-out tip $head" >&2
    return 1
  fi

  # Later steps (build_provenance_dart_defines.sh) compare HEAD with Codemagic's
  # CM_COMMIT, the cloned tip. Record the tip so they can accept this checkout.
  if [[ -n "${CM_BUILD_ID:-}" && -z "${CM_ENV:-}" ]]; then
    echo "CM_ENV is unset; cannot record the cloned tip for later steps" >&2
    return 1
  fi
  local tip="$head"
  git checkout --quiet --detach "$pin"
  head="$(git rev-parse HEAD)"
  if [[ "$head" != "$pin" ]]; then
    echo "checkout of dispatcher source pin $pin left HEAD at $head" >&2
    return 1
  fi
  if [[ -n "${CM_ENV:-}" ]]; then
    echo "OMI_RELEASE_PIN_CLONED_TIP=$tip" >>"$CM_ENV"
  fi
  echo "checked out dispatcher source pin $pin (cloned tip $tip)"
}

main "$@"; exit $?
