#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGE_HELPER="$SCRIPT_DIR/../scripts/qualification-stage.sh"
QUALIFIER="$SCRIPT_DIR/../scripts/qualify-desktop-beta.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-qualification-stage-test.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

create_stage() {
  TMPDIR="$TMP_ROOT" bash -c 'source "$1"; qualification_stage_create' _ "$STAGE_HELPER"
}

stage_one="$(create_stage)"
stage_two="$(create_stage)"
[[ "$stage_one" != "$stage_two" ]] || fail "parallel qualifications reused a stage"
for stage in "$stage_one" "$stage_two"; do
  [[ -d "$stage" ]] || fail "stage does not exist: $stage"
  [[ "$(stat -f '%Lp' "$stage")" == "700" ]] || fail "stage is not owner-only: $stage"
  printf '%s\n' "$stage" >"$stage/release.json"
  printf '%s\n' "$stage" >"$stage/release-body.md"
done
[[ "$(<"$stage_one/release.json")" == "$stage_one" ]] || fail "first stage release input leaked"
[[ "$(<"$stage_two/release.json")" == "$stage_two" ]] || fail "second stage release input leaked"

# The qualifier must create this owner-only per-run stage before its first
# release read and must not route release inputs, evidence, or body state through
# fixed paths under /tmp.
stage_line="$(grep -n 'qualification_stage_create' "$QUALIFIER" | head -n 1 | cut -d: -f1)"
release_line="$(grep -n 'gh release view' "$QUALIFIER" | head -n 1 | cut -d: -f1)"
[[ -n "$stage_line" && -n "$release_line" && "$stage_line" -lt "$release_line" ]] \
  || fail "qualification stage must exist before release reads"
if grep -Eq '(/tmp/(desktop-qualification|qualification-evidence|desktop-qualification-release-body)|EVIDENCE_FILE="/tmp|BODY_FILE=/tmp)' "$QUALIFIER"; then
  fail "qualifier retains fixed shared /tmp qualification state"
fi

echo "qualification stage isolation regression tests passed"
