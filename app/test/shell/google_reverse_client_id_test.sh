#!/usr/bin/env bash
#
# Behavioral tests for the GOOGLE_REVERSE_CLIENT_ID resolution chain.
#
# Runner/Info.plist emits this value as a CFBundleURLSchemes entry, so an empty
# value ships a malformed URL scheme and the Google Sign-In redirect has nowhere
# to land.
#
# Regression covered: the value used to be hardcoded in devDebug.xcconfig. When
# that duplicate was removed in favour of the generator, community builds lost it
# entirely — the prebuilt community Firebase config carries no REVERSED_CLIENT_ID,
# so the generator wrote an empty assignment, and because Custom.xcconfig is
# included AFTER Base.xcconfig that empty value overrode the default rather than
# falling back to it. Two separate code reviews checked that the generator still
# wrote the key and missed that it wrote nothing useful, which is why this asserts
# the resolved value rather than the mechanism.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${SCRIPT_DIR}/../.."
GENERATOR="${APP_DIR}/scripts/generate_ios_custom_config.sh"
BASE_XCCONFIG="${APP_DIR}/ios/Flutter/Base.xcconfig"
COMMUNITY_PLIST="${APP_DIR}/setup/prebuilt/GoogleService-Info-Local.plist"

failures=0
pass() { echo "  ok   - $1"; }
fail() { echo "  FAIL - $1" >&2; failures=$((failures + 1)); }

for f in "$GENERATOR" "$BASE_XCCONFIG" "$COMMUNITY_PLIST"; do
  [[ -f "$f" ]] || { echo "FAIL: missing $f" >&2; exit 1; }
done

# Resolve the key the way Xcode does: later includes win, so read Base first and
# let a generated Custom.xcconfig override it.
resolve_key() {
  local key="$1" custom="$2" value=""
  local line
  while IFS= read -r line; do
    [[ "$line" == "${key}="* ]] && value="${line#*=}"
  done < <(cat "$BASE_XCCONFIG" "$custom" 2>/dev/null)
  printf '%s' "$value"
}

echo "GOOGLE_REVERSE_CLIENT_ID resolution:"

# 1. The community Firebase config has no REVERSED_CLIENT_ID, so the generator
#    must leave the default standing rather than blanking it.
work=$(mktemp -d -t omi_grci_a_XXXXXX)
bash "$GENERATOR" "$COMMUNITY_PLIST" "$work" >/dev/null 2>&1
resolved=$(resolve_key GOOGLE_REVERSE_CLIENT_ID "$work/Custom.xcconfig")
if [[ -n "$resolved" ]]; then
  pass "community config resolves to a non-empty value ($resolved)"
else
  fail "community config resolved to EMPTY — Info.plist would emit an empty URL scheme"
fi
if grep -q "^GOOGLE_REVERSE_CLIENT_ID=$" "$work/Custom.xcconfig" 2>/dev/null; then
  fail "generator wrote an empty assignment, which overrides the Base default"
else
  pass "generator writes no empty assignment for a plist without the key"
fi
rm -rf "$work"

# 2. A plist that does carry the key must still override the default, or every
#    developer would silently build against the checked-in fallback.
work=$(mktemp -d -t omi_grci_b_XXXXXX)
cat > "$work/GoogleService-Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>REVERSED_CLIENT_ID</key>
  <string>com.googleusercontent.apps.123456789-testfixturevalue</string>
</dict>
</plist>
PLIST
bash "$GENERATOR" "$work/GoogleService-Info.plist" "$work" >/dev/null 2>&1
resolved=$(resolve_key GOOGLE_REVERSE_CLIENT_ID "$work/Custom.xcconfig")
if [[ "$resolved" == "com.googleusercontent.apps.123456789-testfixturevalue" ]]; then
  pass "a plist carrying the key overrides the Base default"
else
  fail "expected the plist's value to win, resolved '$resolved'"
fi
rm -rf "$work"

# 3. Base.xcconfig must carry the default at all. Without it there is nothing to
#    fall back to, which is the state that produced the defect.
if grep -qE "^GOOGLE_REVERSE_CLIENT_ID=.+" "$BASE_XCCONFIG"; then
  pass "Base.xcconfig provides a non-empty default"
else
  fail "Base.xcconfig has no GOOGLE_REVERSE_CLIENT_ID default to fall back to"
fi

echo
if [[ "$failures" -gt 0 ]]; then
  echo "$failures shell test(s) failed" >&2
  exit 1
fi
echo "all GOOGLE_REVERSE_CLIENT_ID shell tests passed"
