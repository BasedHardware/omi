#!/usr/bin/env bash
#
# Behavioral tests for check_ios_prerequisites() and its _version_at_least()
# helper in app/setup.sh.
#
# Regression covered: setup.sh printed a prerequisite list (Xcode, CocoaPods,
# Flutter versions) but validated almost none of it, so a missing or outdated
# tool surfaced as a confusing downstream failure several minutes into a
# build instead of a named error with a remedy, unlike the harness's own
# `Cannot start; missing prerequisites:` pattern.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_SH="${SCRIPT_DIR}/../../setup.sh"

if [[ ! -f "$SETUP_SH" ]]; then
  echo "FAIL: cannot find setup.sh at $SETUP_SH" >&2
  exit 1
fi

failures=0
pass() { echo "  ok   - $1"; }
fail() { echo "  FAIL - $1" >&2; failures=$((failures + 1)); }

HARNESS="$(mktemp -t omi_ios_prereq_XXXXXX)"
trap 'rm -f "$HARNESS"' EXIT

extract_function() {
  awk -v fn="function $1()" '
    index($0, fn) == 1 { capture = 1 }
    capture { print }
    capture && $0 == "}" { exit }
  ' "$SETUP_SH"
}

{
  echo "set -uo pipefail"
  extract_function _version_at_least
  extract_function check_ios_prerequisites
} > "$HARNESS"

if ! bash -n "$HARNESS"; then
  echo "FAIL: extracted harness is not valid bash" >&2
  exit 1
fi

# Builds a stub bin/ directory reporting the given tool versions, plus real
# coreutils (bash, sort, grep, awk, printf) so the harness itself still runs.
stub_toolchain() {
  local root="$1" flutter_version="$2" xcode_version="$3" pod_version="$4" have_jq="$5"
  mkdir -p "$root/bin"
  for real in bash sort grep awk printf head cat; do
    ln -sf "$(command -v "$real")" "$root/bin/$real"
  done
  if [[ -n "$flutter_version" ]]; then
    cat > "$root/bin/flutter" <<EOF
#!/usr/bin/env bash
[[ "\$1" == "--version" ]] && echo "Flutter ${flutter_version} • channel stable • https://github.com/flutter/flutter.git"
exit 0
EOF
    chmod +x "$root/bin/flutter"
  fi
  if [[ "$xcode_version" == "broken" ]]; then
    # xcodebuild is on PATH but produces no "Xcode X.Y" line — an unaccepted
    # license or missing components, matching the real command's behavior.
    cat > "$root/bin/xcodebuild" <<'EOF'
#!/usr/bin/env bash
echo "xcodebuild: error: unable to build chip due to missing license agreement." >&2
exit 1
EOF
    chmod +x "$root/bin/xcodebuild"
  elif [[ -n "$xcode_version" ]]; then
    cat > "$root/bin/xcodebuild" <<EOF
#!/usr/bin/env bash
[[ "\$1" == "-version" ]] && printf 'Xcode %s\nBuild version 0000000\n' "${xcode_version}"
exit 0
EOF
    chmod +x "$root/bin/xcodebuild"
  fi
  if [[ -n "$pod_version" ]]; then
    cat > "$root/bin/pod" <<EOF
#!/usr/bin/env bash
[[ "\$1" == "--version" ]] && echo "${pod_version}"
exit 0
EOF
    chmod +x "$root/bin/pod"
  fi
  if [[ "$have_jq" == "yes" ]]; then
    ln -sf "$(command -v jq)" "$root/bin/jq" 2>/dev/null || true
  fi
}

run_with_toolchain() {
  local root="$1"
  PATH="$root/bin" bash -c "source '$HARNESS'; check_ios_prerequisites" 2>&1
}

echo "_version_at_least:"
{
  source "$HARNESS"
  if _version_at_least "16.4" "16.4"; then pass "equal versions satisfy the minimum"; else fail "16.4 should satisfy a 16.4 minimum"; fi
  if _version_at_least "17.0" "16.4"; then pass "newer major version satisfies an older minimum"; else fail "17.0 should satisfy a 16.4 minimum"; fi
  if ! _version_at_least "16.3" "16.4"; then pass "older version fails a newer minimum"; else fail "16.3 should not satisfy a 16.4 minimum"; fi
  if _version_at_least "1.16.2" "1.16.2"; then pass "three-component versions compare correctly"; else fail "1.16.2 should satisfy a 1.16.2 minimum"; fi
}

echo "check_ios_prerequisites:"

root=$(mktemp -d -t omi_ios_prereq_all_ok_XXXXXX)
stub_toolchain "$root" "3.44.9" "16.4" "1.16.2" "yes"
out=$(run_with_toolchain "$root"); rc=$?
rm -rf "$root"
if [[ "$rc" -eq 0 ]]; then
  pass "passes when every tool meets its minimum version"
else
  fail "expected success with all prerequisites met, got: $out"
fi

root=$(mktemp -d -t omi_ios_prereq_old_flutter_XXXXXX)
stub_toolchain "$root" "3.40.0" "16.4" "1.16.2" "yes"
out=$(run_with_toolchain "$root"); rc=$?
rm -rf "$root"
if [[ "$rc" -ne 0 ]] && [[ "$out" == *"Flutter 3.40.0 found"* ]]; then
  pass "names an outdated Flutter version with the found version and a remedy"
else
  fail "expected a named outdated-Flutter failure, got (rc=$rc): $out"
fi

root=$(mktemp -d -t omi_ios_prereq_broken_xcode_XXXXXX)
stub_toolchain "$root" "3.44.9" "broken" "1.16.2" "yes"
out=$(run_with_toolchain "$root"); rc=$?
rm -rf "$root"
if [[ "$rc" -ne 0 ]] && [[ "$out" == *"xcodebuild is on PATH but not usable"* ]]; then
  pass "names an unaccepted-license/broken Xcode install, not a silent pass"
else
  fail "expected a named broken-xcodebuild failure, got (rc=$rc): $out"
fi

root=$(mktemp -d -t omi_ios_prereq_no_xcode_XXXXXX)
stub_toolchain "$root" "3.44.9" "" "1.16.2" "yes"
out=$(run_with_toolchain "$root"); rc=$?
rm -rf "$root"
if [[ "$rc" -ne 0 ]] && [[ "$out" == *"Xcode (v16.4 or later)"* ]]; then
  pass "names a missing Xcode with a remedy"
else
  fail "expected a named missing-Xcode failure, got (rc=$rc): $out"
fi

root=$(mktemp -d -t omi_ios_prereq_old_pods_XXXXXX)
stub_toolchain "$root" "3.44.9" "16.4" "1.10.0" "yes"
out=$(run_with_toolchain "$root"); rc=$?
rm -rf "$root"
if [[ "$rc" -ne 0 ]] && [[ "$out" == *"CocoaPods 1.10.0 found"* ]]; then
  pass "names an outdated CocoaPods version with the found version and a remedy"
else
  fail "expected a named outdated-CocoaPods failure, got (rc=$rc): $out"
fi

root=$(mktemp -d -t omi_ios_prereq_no_jq_XXXXXX)
stub_toolchain "$root" "3.44.9" "16.4" "1.16.2" "no"
out=$(run_with_toolchain "$root"); rc=$?
rm -rf "$root"
if [[ "$rc" -ne 0 ]] && [[ "$out" == *"jq (used to select"* ]]; then
  pass "names missing jq with a remedy"
else
  fail "expected a named missing-jq failure, got (rc=$rc): $out"
fi

root=$(mktemp -d -t omi_ios_prereq_all_missing_XXXXXX)
stub_toolchain "$root" "" "" "" "no"
out=$(run_with_toolchain "$root"); rc=$?
missing_count=$(printf '%s\n' "$out" | grep -c '^   - ')
rm -rf "$root"
if [[ "$rc" -ne 0 ]] && [[ "$missing_count" -eq 4 ]]; then
  pass "names all four missing prerequisites at once, not just the first"
else
  fail "expected 4 named prerequisites, got $missing_count (rc=$rc): $out"
fi

echo
if [[ "$failures" -gt 0 ]]; then
  echo "$failures shell test(s) failed" >&2
  exit 1
fi
echo "all iOS prerequisite shell tests passed"
