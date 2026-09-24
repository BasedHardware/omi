#!/usr/bin/env bash
# Before/after screenshots of the registered visual audit scenarios at two revisions.
# Docs: app/e2e/SKILL.md, "Visual audit". Screenshots are never committed.
#
#   app/scripts/visual_audit.sh --base <rev> --head <rev> [--only id,id] [--out DIR]
#   app/scripts/visual_audit.sh --head WORKTREE [--only ...]   # this checkout as it is, one side
#   app/scripts/visual_audit.sh --list
#
# Each revision is checked out in a temporary detached worktree under $OMI_WORKTREES (default:
# the system temp dir), prepared like CI (generated files, pub get, build_runner), and removed on
# exit. The scenarios and harness come from THIS checkout's app/integration_test/visual_audit/,
# copied over both sides, so both are captured by the same registry. A scenario must therefore
# compile against both revisions.
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="$(git -C "$app_dir" rev-parse --show-toplevel)"
tool_dir="$app_dir/integration_test/visual_audit"

usage() { sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

base='' head='' only='' out=''
while (($#)); do
  case "$1" in
    --base) base="${2:?--base needs a revision}"; shift 2 ;;
    --head) head="${2:?--head needs a revision}"; shift 2 ;;
    --only) only="${2:?--only needs comma-separated ids}"; shift 2 ;;
    --out) out="${2:?--out needs a directory}"; shift 2 ;;
    --list)
      grep -h -A1 "AuditScenario(" "$tool_dir"/scenarios/*.dart | sed -n "s/^ *id: '\(.*\)',$/\1/p"
      exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ -n "$head" ]] || { usage >&2; exit 2; }
if [[ -n "$only" ]]; then
  known="$("${BASH_SOURCE[0]}" --list)"
  for id in ${only//,/ }; do
    grep -qx "$id" <<<"$known" || { echo "Unknown scenario id: $id (see --list)" >&2; exit 2; }
  done
fi

out="${out:-$(mktemp -d "${TMPDIR:-/tmp}/omi-visual-audit-XXXXXX")}"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
case "$out/" in
  "$repo_root"/*) echo "Output must be outside the repository (screenshots are never committed): $out" >&2; exit 2 ;;
esac
[[ -z "$(ls -A "$out")" ]] || { echo "Output directory must be empty (no stale evidence): $out" >&2; exit 2; }

worktree_root="${OMI_WORKTREES:-${TMPDIR:-/tmp}}"
stamp="visual-audit-$(date -u +%Y%m%dT%H%M%SZ)-$$"
worktrees=()
# One snapshot of the harness and registry, so both sides run exactly the same scenarios.
snapshot="$(mktemp -d "${TMPDIR:-/tmp}/omi-visual-audit-harness-XXXXXX")"
cp -R "$tool_dir" "$snapshot/visual_audit"
cleanup() {
  rm -rf "$snapshot"
  for wt in ${worktrees[@]+"${worktrees[@]}"}; do
    git -C "$repo_root" worktree remove --force "$wt" >/dev/null 2>&1 || echo "Could not remove worktree $wt" >&2
  done
}
trap cleanup EXIT

# Generated files exactly as the mobile CI job makes them (hermetic, loopback-only API).
prepare() {
  local app="$1"
  (
    cd "$app"
    cp lib/firebase_options_local.dart lib/firebase_options_dev.dart
    cp lib/firebase_options_local.dart lib/firebase_options_prod.dart
    printf 'API_BASE_URL=\nUSE_WEB_AUTH=true\nUSE_AUTH_CUSTOM_TOKEN=true\nSTAGING_API_URL=\n' > .dev.env
    : > .env
    flutter pub get
    dart run build_runner build --delete-conflicting-outputs
  )
}

# checkout SIDE REV: sets app_of_SIDE to the app dir that will be captured, and records the revision.
checkout() {
  local side="$1" rev="$2" sha app
  mkdir -p "$out/$side"
  if [[ "$rev" == WORKTREE ]]; then
    app="$app_dir"
    sha="$(git -C "$repo_root" rev-parse HEAD)"
    [[ -z "$(git -C "$repo_root" status --porcelain)" ]] || sha="$sha+uncommitted"
  else
    sha="$(git -C "$repo_root" rev-parse --verify "$rev^{commit}")"
    local wt="$worktree_root/$stamp-$side"
    git -C "$repo_root" worktree add --detach "$wt" "$sha" >/dev/null
    worktrees+=("$wt")
    app="$wt/app"
    rm -rf "$app/integration_test/visual_audit"
    cp -R "$snapshot/visual_audit" "$app/integration_test/visual_audit"
  fi
  printf '{"rev": "%s", "sha": "%s"}\n' "$rev" "$sha" > "$out/$side/source.json"
  printf -v "app_of_$side" '%s' "$app"
  echo "[$side] $rev = $sha"
}

# capture SIDE: writes $out/SIDE/{*.png,frames.json,scenarios.json,capture.log}. A failing
# scenario is reported and the others still capture.
capture() {
  local side="$1" app_var="app_of_$1" status=0
  local app="${!app_var}"
  bash "$app/scripts/check_hermetic_test_env.sh" --app-dir "$app"
  echo "[$side] capturing"
  (
    cd "$app"
    OMI_AUDIT_OUTPUT="$out/$side" OMI_AUDIT_ONLY="$only" \
      flutter test -d flutter-tester --concurrency=1 integration_test/visual_audit/capture_test.dart --reporter expanded
  ) > "$out/$side/capture.log" 2>&1 || status=$?
  ((status == 0)) || echo "[$side] some scenarios failed (exit $status): $out/$side/capture.log" >&2
}

sides=()
[[ -z "$base" ]] || { checkout before "$base"; sides+=(before); }
checkout after "$head"
sides+=(after)

# Prepare the temporary worktrees in parallel; capture one side at a time.
pids=()
for side in "${sides[@]}"; do
  app_var="app_of_$side"
  [[ "${!app_var}" == "$app_dir" ]] && continue
  echo "[$side] preparing (log: $out/$side/prepare.log)"
  prepare "${!app_var}" > "$out/$side/prepare.log" 2>&1 &
  pids+=("$!:$side")
done
for entry in ${pids[@]+"${pids[@]}"}; do
  wait "${entry%%:*}" || { echo "[${entry#*:}] prepare failed: $out/${entry#*:}/prepare.log" >&2; exit 1; }
done
for side in "${sides[@]}"; do
  capture "$side"
done

command="app/scripts/visual_audit.sh${base:+ --base $base} --head $head${only:+ --only $only}"
python3 "$tool_dir/write_gallery.py" "$out" --command "$command"
echo "Visual audit: $out (open gallery.html; INDEX.md lists SHAs and capture times)"
