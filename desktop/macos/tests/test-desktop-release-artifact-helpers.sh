#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NOTARIZE_HELPER="$MACOS_DIR/scripts/notarize-desktop-artifacts.sh"
DMG_HELPER="$MACOS_DIR/scripts/create-desktop-dmgs.sh"
BETA_HELPER="$MACOS_DIR/scripts/create-omi-beta-variant.sh"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-release-helper-test.XXXXXX")"
MOCK_BIN="$TEST_ROOT/bin"
EVENTS="$TEST_ROOT/events"
mkdir -p \
  "$MOCK_BIN" \
  "$TEST_ROOT/apps/Omi.app/Contents/Resources" \
  "$TEST_ROOT/apps/Omi Beta.app/Contents" \
  "$TEST_ROOT/beta-work/Desktop/.build/artifacts/sparkle/Sparkle/bin" \
  "$TEST_ROOT/beta-work/build"
: > "$EVENTS"
trap 'rm -rf "$TEST_ROOT"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

cat > "$MOCK_BIN/ditto" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
source_path="${@: -2:1}"
destination="${@: -1}"
if [[ " $* " == *" -c "* ]]; then
  : > "$destination"
else
  cp -R "$source_path" "$destination"
fi
STUB

cat > "$MOCK_BIN/codesign" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'codesign %s\n' "$*" >> "$STUB_EVENTS"
STUB

cat > "$MOCK_BIN/xattr" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

cat > "$MOCK_BIN/xcrun" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "notarytool" && "${2:-}" == "submit" ]]; then
  artifact="$3"
  case "$artifact" in
    *stable*) label=stable ;;
    *beta*) label=beta ;;
    *) echo "unknown stub identity: $artifact" >&2; exit 9 ;;
  esac
  printf 'submit %s\n' "$label" >> "$STUB_EVENTS"
  if [[ -n "${STUB_NOTARY_BARRIER:-}" ]]; then
    [[ "$label" == stable ]] && peer=beta || peer=stable
    : > "$STUB_NOTARY_BARRIER/$label.started"
    for ((attempt = 0; attempt < 5000000; attempt++)); do
      [[ -f "$STUB_NOTARY_BARRIER/$peer.started" ]] && break
    done
    [[ -f "$STUB_NOTARY_BARRIER/$peer.started" ]] || {
      echo "$label notary submission did not overlap $peer" >&2
      exit 7
    }
  fi
  if [[ "${STUB_FAIL_LABEL:-}" == "$label" ]]; then
    printf '{"id":"%s-id","status":"Invalid"}\n' "$label"
  else
    printf '{"id":"%s-id","status":"Accepted"}\n' "$label"
  fi
elif [[ "${1:-}" == "notarytool" && "${2:-}" == "log" ]]; then
  printf 'notary-log %s\n' "$3" >> "$STUB_EVENTS"
elif [[ "${1:-}" == "stapler" ]]; then
  printf '%s %s\n' "$2" "${3:-}" >> "$STUB_EVENTS"
else
  echo "unexpected xcrun invocation: $*" >&2
  exit 8
fi
STUB

cat > "$MOCK_BIN/dmgbuild" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
output="${@: -1}"
case "$output" in
  *stable*) label=stable; peer=beta ;;
  *beta*) label=beta; peer=stable ;;
  *) echo "unknown stub identity: $output" >&2; exit 9 ;;
esac
printf 'dmgbuild %s\n' "$label" >> "$STUB_EVENTS"
: > "$STUB_BARRIER/$label.started"
for ((attempt = 0; attempt < 5000000; attempt++)); do
  [[ -f "$STUB_BARRIER/$peer.started" ]] && break
done
[[ -f "$STUB_BARRIER/$peer.started" ]] || {
  echo "$label did not overlap $peer" >&2
  exit 7
}
if [[ "${STUB_FAIL_LABEL:-}" == "$label" ]]; then
  exit 6
fi
: > "$output"
STUB
chmod +x "$MOCK_BIN"/*

cat > "$TEST_ROOT/apps/Omi.app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>com.omi.computer-macos</string>
  <key>CFBundleName</key><string>Omi</string>
  <key>CFBundleDisplayName</key><string>Omi</string>
  <key>SUFeedURL</key><string>https://api.omi.me/v2/desktop/appcast.xml</string>
</dict></plist>
PLIST
cat > "$TEST_ROOT/apps/Omi.app/Contents/Resources/.env" <<'ENV'
OMI_PYTHON_API_URL=https://api.omi.me/
OMI_DESKTOP_API_URL=https://desktop.omi.me/
ENV
cat > "$TEST_ROOT/beta-work/Desktop/.build/artifacts/sparkle/Sparkle/bin/sign_update" <<'STUB'
#!/usr/bin/env bash
printf 'sparkle:edSignature="stub-beta-signature" length="1"\n'
STUB
chmod +x "$TEST_ROOT/beta-work/Desktop/.build/artifacts/sparkle/Sparkle/bin/sign_update"

export PATH="$MOCK_BIN:/usr/bin:/bin"
export STUB_EVENTS="$EVENTS"
export APP_STORE_CONNECT_KEY_IDENTIFIER="stub-key"
export APP_STORE_CONNECT_PRIVATE_KEY="stub-private-key"
export APP_STORE_CONNECT_ISSUER_ID="stub-issuer"
export SIGN_IDENTITY="Developer ID Stub"

# Preparation changes only the copied Beta identity/authorities; Sparkle is a
# separate phase that creates the ZIP and exports its signature.
(
  cd "$TEST_ROOT/beta-work"
  "$BETA_HELPER" \
    --phase prepare \
    --source-app "$TEST_ROOT/apps/Omi.app" \
    --build-dir "$TEST_ROOT/beta-work/build"
)
PREPARED_APP="$TEST_ROOT/beta-work/build/Omi Beta.app"
if grep -Eq '^submit ' "$EVENTS"; then
  fail "prepare phase contacted Apple notarization"
fi
[[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$PREPARED_APP/Contents/Info.plist")" == \
  "com.omi.computer-macos.beta" ]] || fail "prepare phase did not patch the Beta bundle identity"
[[ "$(/usr/libexec/PlistBuddy -c 'Print :SUFeedURL' "$PREPARED_APP/Contents/Info.plist")" == \
  "https://api.omi.me/v2/desktop/appcast.xml?identity=beta" ]] || fail "prepare phase did not patch the Beta feed"
grep -Fqx 'OMI_PYTHON_API_URL=https://api.omiapi.com/' "$PREPARED_APP/Contents/Resources/.env" \
  || fail "prepare phase did not patch the Beta Python authority"
(
  cd "$TEST_ROOT/beta-work"
  SPARKLE_PRIVATE_KEY=stub-key "$BETA_HELPER" \
    --phase sparkle \
    --build-dir "$TEST_ROOT/beta-work/build" \
    --sparkle-zip-out "$TEST_ROOT/beta-work/build/Omi.Beta.zip" \
    --cm-env "$TEST_ROOT/beta-work/cm-env"
)
[[ -f "$TEST_ROOT/beta-work/build/Omi.Beta.zip" ]] || fail "sparkle phase did not create the Beta ZIP"
grep -Fqx 'BETA_ED_SIGNATURE=stub-beta-signature' "$TEST_ROOT/beta-work/cm-env" \
  || fail "sparkle phase did not export BETA_ED_SIGNATURE"

# A rejected identity still waits for and attributes both submissions, and no
# artifact is stapled when the accepted set is incomplete.
if STUB_FAIL_LABEL=stable "$NOTARIZE_HELPER" \
  --kind app \
  --work-dir "$TEST_ROOT/notary-failure" \
  --artifact stable "$TEST_ROOT/apps/Omi.app" \
  --artifact beta "$TEST_ROOT/apps/Omi Beta.app" \
  >"$TEST_ROOT/notary-failure.out" 2>"$TEST_ROOT/notary-failure.err"; then
  fail "notarization helper accepted one failed identity"
fi
grep -Fqx 'submit stable' "$EVENTS" || fail "stable identity was not submitted"
grep -Fqx 'submit beta' "$EVENTS" || fail "beta identity was not submitted"
grep -Fq 'identity stable' "$TEST_ROOT/notary-failure.err" || fail "failed notary identity was not attributed"
if grep -Eq '^staple ' "$EVENTS"; then
  fail "notarization helper stapled before every identity was accepted"
fi
if find "$TEST_ROOT/notary-failure" -name 'AuthKey_*.p8' -print -quit | grep -q .; then
  fail "temporary notary key was retained after failure"
fi

: > "$EVENTS"
mkdir -p "$TEST_ROOT/notary-success-barrier"
export STUB_NOTARY_BARRIER="$TEST_ROOT/notary-success-barrier"
"$NOTARIZE_HELPER" \
  --kind app \
  --work-dir "$TEST_ROOT/notary-success" \
  --artifact stable "$TEST_ROOT/apps/Omi.app" \
  --artifact beta "$TEST_ROOT/apps/Omi Beta.app"
unset STUB_NOTARY_BARRIER
[[ "$(grep -c '^staple ' "$EVENTS")" -eq 2 ]] || fail "successful notarization did not staple both identities"

# DMG notarization signs both independent images before submission.
: > "$EVENTS"
: > "$TEST_ROOT/stable-notary.dmg"
: > "$TEST_ROOT/beta-notary.dmg"
"$NOTARIZE_HELPER" \
  --kind dmg \
  --work-dir "$TEST_ROOT/notary-dmg-success" \
  --artifact stable "$TEST_ROOT/stable-notary.dmg" \
  --artifact beta "$TEST_ROOT/beta-notary.dmg"
[[ "$(grep -c '^codesign --force --sign .*notary\.dmg$' "$EVENTS")" -eq 2 ]] || fail "both DMGs were not signed"
[[ "$(grep -c '^submit ' "$EVENTS")" -eq 2 ]] || fail "both signed DMGs were not submitted"
[[ "$(grep -c '^staple ' "$EVENTS")" -eq 2 ]] || fail "both accepted DMGs were not stapled"

# The DMG helper must overlap the two dmgbuild processes and produce both
# independently staged outputs.
: > "$EVENTS"
mkdir -p "$TEST_ROOT/barrier-success"
export STUB_BARRIER="$TEST_ROOT/barrier-success"
"$DMG_HELPER" \
  --work-dir "$TEST_ROOT/dmg-success" \
  --dmg stable "$TEST_ROOT/apps/Omi.app" "Omi" "$TEST_ROOT/out/stable.dmg" \
  --dmg beta "$TEST_ROOT/apps/Omi Beta.app" "Omi Beta" "$TEST_ROOT/out/beta.dmg"
[[ -f "$TEST_ROOT/out/stable.dmg" ]] || fail "stable DMG was not produced"
[[ -f "$TEST_ROOT/out/beta.dmg" ]] || fail "beta DMG was not produced"
grep -Fqx 'dmgbuild stable' "$EVENTS" || fail "stable DMG identity was not attempted"
grep -Fqx 'dmgbuild beta' "$EVENTS" || fail "beta DMG identity was not attempted"

: > "$EVENTS"
mkdir -p "$TEST_ROOT/barrier-failure"
export STUB_BARRIER="$TEST_ROOT/barrier-failure"
if STUB_FAIL_LABEL=beta "$DMG_HELPER" \
  --work-dir "$TEST_ROOT/dmg-failure" \
  --dmg stable "$TEST_ROOT/apps/Omi.app" "Omi" "$TEST_ROOT/out/fail-stable.dmg" \
  --dmg beta "$TEST_ROOT/apps/Omi Beta.app" "Omi Beta" "$TEST_ROOT/out/fail-beta.dmg" \
  >"$TEST_ROOT/dmg-failure.out" 2>"$TEST_ROOT/dmg-failure.err"; then
  fail "DMG helper accepted one failed identity"
fi
grep -Fq 'identity beta' "$TEST_ROOT/dmg-failure.err" || fail "failed DMG identity was not attributed"
grep -Fqx 'dmgbuild stable' "$EVENTS" || fail "stable DMG was not attempted after peer failure"
grep -Fqx 'dmgbuild beta' "$EVENTS" || fail "beta DMG was not attempted"

echo "desktop release artifact helpers preserve parallel, fail-closed identity handling"
