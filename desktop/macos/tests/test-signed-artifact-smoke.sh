#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SMOKE="$MACOS_DIR/scripts/smoke-signed-desktop-artifact.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMP_ROOTS=()
cleanup() {
  for path in "${TMP_ROOTS[@]:-}"; do
    [[ -n "$path" ]] && rm -rf "$path"
  done
}
trap cleanup EXIT

[[ -x "$SMOKE" ]] || fail "signed artifact smoke script must be executable"

if ! "$SMOKE" --help >/tmp/omi-smoke-help.out; then
  fail "--help should succeed"
fi

python3 - "$SMOKE" <<'PY'
import ast
import re
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r're\.fullmatch\((r"[^"]+")\s*, marker\)', source)
if match is None:
    raise SystemExit("notification callback marker parser is missing")
pattern = ast.literal_eval(match.group(1))
if re.fullmatch(pattern, "main_actor=true authorization_status=0") is None:
    raise SystemExit("notification callback marker parser must accept a numeric authorization status")
PY

for required in \
  "Launch + identity" \
  "Auth persistence" \
  "Signed Keychain canary" \
  "Backend routing" \
  "Sparkle/update metadata" \
  "External-preview isolation" \
  "Native helper/runtime bundle integrity" \
  "Minimal chat path" \
  "Recording permission surface sanity" \
  "Local storage/database"; do
  grep -q "$required" /tmp/omi-smoke-help.out || fail "help is missing smoke path: $required"
done

if "$SMOKE" --tag "bad-tag" >/tmp/omi-smoke-invalid.out 2>/tmp/omi-smoke-invalid.err; then
  fail "missing app should fail"
fi
grep -q -- "--app or --zip is required" /tmp/omi-smoke-invalid.err || fail "missing app failure should be explicit"

if "$SMOKE" --app --zip file.zip >/tmp/omi-smoke-missing-value.out 2>/tmp/omi-smoke-missing-value.err; then
  fail "missing option value should fail"
fi
grep -q -- "--app requires a value" /tmp/omi-smoke-missing-value.err || fail "missing value failure should be explicit"

if "$SMOKE" --expected-bundle-id --preview >/tmp/omi-smoke-preview-missing-value.out 2>/tmp/omi-smoke-preview-missing-value.err; then
  fail "missing external preview identity should fail"
fi
grep -q -- "--expected-bundle-id requires a value" /tmp/omi-smoke-preview-missing-value.err \
  || fail "preview identity failure should be explicit"

tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/omi-smoke-test.XXXXXX")"
TMP_ROOTS+=("$tmp_root")
tmp_app="$tmp_root/Omi.app"
mkdir -p "$tmp_app/Contents/MacOS" "$tmp_app/Contents/Resources" "$tmp_app/Contents/Frameworks"
cat > "$tmp_app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>Omi Computer</string>
  <key>CFBundleIdentifier</key><string>com.omi.computer-macos</string>
  <key>CFBundleShortVersionString</key><string>0.12.34</string>
  <key>CFBundleVersion</key><string>12034</string>
  <key>CFBundleURLTypes</key>
  <array><dict><key>CFBundleURLSchemes</key><array><string>omi-computer</string></array></dict></array>
  <key>SUFeedURL</key><string>https://api.omi.me/v2/desktop/appcast.xml</string>
</dict>
</plist>
PLIST
touch "$tmp_app/Contents/MacOS/Omi Computer"
chmod +x "$tmp_app/Contents/MacOS/Omi Computer"

if "$SMOKE" --app "$tmp_app" --tag "bad-tag" >/tmp/omi-smoke-badtag.out 2>/tmp/omi-smoke-badtag.err; then
  fail "bad release tag should fail before signing checks"
fi
grep -q "invalid release tag" /tmp/omi-smoke-badtag.err || fail "bad tag failure should be explicit"

# Omi Beta variant: identity-scoped feed URL is accepted only when passed
# explicitly; the default expectation stays the plain shared feed.
beta_app="$tmp_root/Omi Beta.app"
mkdir -p "$beta_app/Contents/MacOS" "$beta_app/Contents/Resources" "$beta_app/Contents/Frameworks"
cat > "$beta_app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>Omi Computer</string>
  <key>CFBundleIdentifier</key><string>com.omi.computer-macos.beta</string>
  <key>CFBundleShortVersionString</key><string>0.12.34</string>
  <key>CFBundleVersion</key><string>12034</string>
  <key>CFBundleURLTypes</key>
  <array><dict><key>CFBundleURLSchemes</key><array><string>omi-computer</string></array></dict></array>
  <key>SUFeedURL</key><string>https://api.omi.me/v2/desktop/appcast.xml?identity=beta</string>
</dict>
</plist>
PLIST
touch "$beta_app/Contents/MacOS/Omi Computer"
chmod +x "$beta_app/Contents/MacOS/Omi Computer"

if "$SMOKE" --app "$beta_app" --tag "v0.12.34+12034-macos" \
  --expected-bundle-id com.omi.computer-macos.beta \
  >/tmp/omi-smoke-beta-default.out 2>/tmp/omi-smoke-beta-default.err; then
  fail "beta feed URL must be rejected without --expected-feed-url"
fi
grep -q "SUFeedURL mismatch" /tmp/omi-smoke-beta-default.err \
  || fail "default feed expectation should reject the identity-scoped feed"

if "$SMOKE" --app "$beta_app" --tag "v0.12.34+12034-macos" \
  --expected-bundle-id com.omi.computer-macos.beta \
  --expected-feed-url "https://api.omi.me/v2/desktop/appcast.xml?identity=beta" \
  >/tmp/omi-smoke-beta-feed.out 2>/tmp/omi-smoke-beta-feed.err; then
  fail "unsigned fixture should still fail later (signing), not pass entirely"
fi
grep -q "SUFeedURL mismatch" /tmp/omi-smoke-beta-feed.err \
  && fail "--expected-feed-url should accept the identity-scoped feed"

make_signed_smoke_fixture() {
  local app="$1"
  local bundle_id="$2"
  local feed_url="$3"
  local python_api_url="${4:-https://api.omi.me}"
  local desktop_api_url="${5:-https://desktop-backend-hhibjajaja-uc.a.run.app/}"

  mkdir -p \
    "$app/Contents/MacOS" \
    "$app/Contents/Frameworks/Sparkle.framework" \
    "$app/Contents/Resources/agent/src/runtime" \
    "$app/Contents/Resources/agent/node_modules/@img/sharp-darwin-arm64/lib" \
    "$app/Contents/Resources/agent/node_modules/@img/sharp-darwin-x64/lib" \
    "$app/Contents/Resources/agent/node_modules/@img/sharp-libvips-darwin-arm64/lib" \
    "$app/Contents/Resources/agent/node_modules/@img/sharp-libvips-darwin-x64/lib" \
    "$app/Contents/Resources/agent/dist/runtime" \
    "$app/Contents/Resources/pi-mono-extension/node_modules/@omi/placeholder" \
    "$app/Contents/Resources/Omi Computer_Omi Computer.bundle/Contents/Resources"
  cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>Omi Computer</string>
  <key>CFBundleIdentifier</key><string>$bundle_id</string>
  <key>CFBundleShortVersionString</key><string>0.12.34</string>
  <key>CFBundleVersion</key><string>12034</string>
  <key>CFBundleURLTypes</key>
  <array><dict><key>CFBundleURLSchemes</key><array><string>omi-computer</string></array></dict></array>
  <key>SUFeedURL</key><string>$feed_url</string>
</dict>
</plist>
PLIST
  printf 'OMI_PYTHON_API_URL=%s\nOMI_DESKTOP_API_URL=%s\n' "$python_api_url" "$desktop_api_url" \
    > "$app/Contents/Resources/.env"
  cat > "$app/Contents/Resources/GoogleService-Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>PROJECT_ID</key><string>based-hardware</string></dict></plist>
PLIST
  printf '#!/usr/bin/env bash\nexit 0\n' > "$app/Contents/MacOS/Omi Computer"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$app/Contents/Resources/Omi Computer_Omi Computer.bundle/Contents/Resources/node"
  chmod +x "$app/Contents/MacOS/Omi Computer" "$app/Contents/Resources/Omi Computer_Omi Computer.bundle/Contents/Resources/node"
  # The runtime payload pi-mono loads after the bridge script. Non-empty on
  # purpose: a zero-byte entry point cannot answer a turn either.
  printf 'runtime\n' > "$app/Contents/Resources/agent/dist/index.js"
  printf 'manifest\n' > "$app/Contents/Resources/agent/dist/runtime/omi-tool-manifest.js"
  printf '{}\n' > "$app/Contents/Resources/agent/package.json"
  printf 'extension\n' > "$app/Contents/Resources/pi-mono-extension/index.ts"
  printf '{}\n' > "$app/Contents/Resources/pi-mono-extension/package.json"
  printf '{}\n' > "$app/Contents/Resources/pi-mono-extension/node_modules/@omi/placeholder/package.json"
  printf '{}\n' > "$app/Contents/Resources/agent/node_modules/@img/sharp-darwin-arm64/package.json"
  touch \
    "$app/Contents/Resources/agent/node_modules/@img/sharp-darwin-arm64/lib/sharp-darwin-arm64.node" \
    "$app/Contents/Resources/agent/node_modules/@img/sharp-darwin-x64/lib/sharp-darwin-x64.node" \
    "$app/Contents/Resources/agent/node_modules/@img/sharp-libvips-darwin-arm64/lib/libvips-cpp.42.dylib" \
    "$app/Contents/Resources/agent/node_modules/@img/sharp-libvips-darwin-x64/lib/libvips-cpp.42.dylib"
}

mock_bin="$tmp_root/mock-bin"
mkdir -p "$mock_bin"
cat > "$mock_bin/codesign" <<'SH'
#!/usr/bin/env bash
if [[ " $* " == *" --entitlements "* ]]; then
  printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict/></plist>'
elif [[ "${1:-}" == "-dv" ]]; then
  printf 'TeamIdentifier=9536L8KLMP\nRuntime Version=15.0.0\n' >&2
fi
SH
cat > "$mock_bin/spctl" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat > "$mock_bin/xcrun" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat > "$mock_bin/hdiutil" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "attach" ]]; then
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-mountpoint" ]]; then
      mountpoint="$2"
      break
    fi
    shift
  done
  cp -R "$OMI_TEST_DMG_APP_SOURCE" "$mountpoint/"
fi
SH
cat > "$mock_bin/file" <<'SH'
#!/usr/bin/env bash
printf '%s: Mach-O 64-bit executable arm64 x86_64\n' "${1:-fixture}"
SH
cat > "$mock_bin/otool" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat > "$mock_bin/strings" <<'SH'
#!/usr/bin/env bash
printf 'LocalAgentAPIServer\nRewindDatabase\n'
SH
chmod +x "$mock_bin"/*

canonical_dmg_app="$tmp_root/Omi.app"
signed_beta_app="$tmp_root/signed/Omi Beta.app"
renamed_canonical_app="$tmp_root/Anything.app"
renamed_beta_app="$tmp_root/signed/Anything Beta.app"
make_signed_smoke_fixture "$canonical_dmg_app" \
  com.omi.computer-macos \
  https://api.omi.me/v2/desktop/appcast.xml
make_signed_smoke_fixture "$signed_beta_app" \
  com.omi.computer-macos.beta \
  'https://api.omi.me/v2/desktop/appcast.xml?identity=beta' \
  https://api.omiapi.com/ \
  https://desktop-backend-dt5lrfkkoa-uc.a.run.app/
make_signed_smoke_fixture "$renamed_canonical_app" \
  com.omi.computer-macos \
  https://api.omi.me/v2/desktop/appcast.xml
make_signed_smoke_fixture "$renamed_beta_app" \
  com.omi.computer-macos.beta \
  'https://api.omi.me/v2/desktop/appcast.xml?identity=beta' \
  https://api.omiapi.com/ \
  https://desktop-backend-dt5lrfkkoa-uc.a.run.app/
# Firebase Web API keys are public client configuration, required for desktop
# sign-in, and bound by the signed GoogleService-Info.plist project check.
printf 'FIREBASE_API_KEY=public-firebase-web-key\n' >> "$signed_beta_app/Contents/Resources/.env"
dummy_dmg="$tmp_root/fixture.dmg"
touch "$dummy_dmg"

PATH="$mock_bin:$PATH" OMI_TEST_DMG_APP_SOURCE="$canonical_dmg_app" \
  "$SMOKE" --app "$canonical_dmg_app" --dmg "$dummy_dmg" \
  --tag v0.12.34+12034-macos \
  >/tmp/omi-smoke-canonical-dmg.out 2>/tmp/omi-smoke-canonical-dmg.err \
  || fail "canonical Omi.app DMG should pass: $(cat /tmp/omi-smoke-canonical-dmg.err)"

PATH="$mock_bin:$PATH" OMI_TEST_DMG_APP_SOURCE="$signed_beta_app" \
  "$SMOKE" --app "$signed_beta_app" --dmg "$dummy_dmg" \
  --tag v0.12.34+12034-macos \
  --expected-bundle-id com.omi.computer-macos.beta \
  --expected-feed-url 'https://api.omi.me/v2/desktop/appcast.xml?identity=beta' \
  --expected-python-api-url https://api.omiapi.com/ \
  --expected-desktop-api-url https://desktop-backend-dt5lrfkkoa-uc.a.run.app/ \
  >/tmp/omi-smoke-beta-dmg.out 2>/tmp/omi-smoke-beta-dmg.err \
  || fail "Omi Beta.app DMG should pass: $(cat /tmp/omi-smoke-beta-dmg.err)"

if PATH="$mock_bin:$PATH" OMI_TEST_DMG_APP_SOURCE="$canonical_dmg_app" \
  "$SMOKE" --app "$signed_beta_app" --dmg "$dummy_dmg" \
  --tag v0.12.34+12034-macos \
  --expected-bundle-id com.omi.computer-macos.beta \
  --expected-feed-url 'https://api.omi.me/v2/desktop/appcast.xml?identity=beta' \
  --expected-python-api-url https://api.omiapi.com/ \
  --expected-desktop-api-url https://desktop-backend-dt5lrfkkoa-uc.a.run.app/ \
  >/tmp/omi-smoke-beta-wrong-dmg.out 2>/tmp/omi-smoke-beta-wrong-dmg.err; then
  fail "beta smoke must reject a DMG containing only Omi.app"
fi
grep -q "DMG must contain exact Omi Beta.app" /tmp/omi-smoke-beta-wrong-dmg.err \
  || fail "wrong-name DMG rejection should name the exact expected bundle"

if PATH="$mock_bin:$PATH" OMI_TEST_DMG_APP_SOURCE="$renamed_canonical_app" \
  "$SMOKE" --app "$renamed_canonical_app" --dmg "$dummy_dmg" \
  --tag v0.12.34+12034-macos \
  >/tmp/omi-smoke-renamed-canonical.out 2>/tmp/omi-smoke-renamed-canonical.err; then
  fail "canonical identity must reject a renamed app and matching DMG"
fi
grep -q "app bundle name for com.omi.computer-macos must be Omi.app, got Anything.app" \
  /tmp/omi-smoke-renamed-canonical.err \
  || fail "renamed canonical rejection should bind Omi.app to its bundle identity"

if PATH="$mock_bin:$PATH" OMI_TEST_DMG_APP_SOURCE="$renamed_beta_app" \
  "$SMOKE" --app "$renamed_beta_app" --dmg "$dummy_dmg" \
  --tag v0.12.34+12034-macos \
  --expected-bundle-id com.omi.computer-macos.beta \
  --expected-feed-url 'https://api.omi.me/v2/desktop/appcast.xml?identity=beta' \
  --expected-python-api-url https://api.omiapi.com/ \
  --expected-desktop-api-url https://desktop-backend-dt5lrfkkoa-uc.a.run.app/ \
  >/tmp/omi-smoke-renamed-beta.out 2>/tmp/omi-smoke-renamed-beta.err; then
  fail "beta identity must reject a renamed app and matching DMG"
fi
grep -q "app bundle name for com.omi.computer-macos.beta must be Omi Beta.app, got Anything Beta.app" \
  /tmp/omi-smoke-renamed-beta.err \
  || fail "renamed beta rejection should bind Omi Beta.app to its bundle identity"

mkdir -p "$tmp_root/wrong-firebase"
wrong_firebase_beta="$tmp_root/wrong-firebase/Omi Beta.app"
cp -R "$signed_beta_app" "$wrong_firebase_beta"
/usr/libexec/PlistBuddy -c 'Set :PROJECT_ID based-hardware-dev' \
  "$wrong_firebase_beta/Contents/Resources/GoogleService-Info.plist"
if PATH="$mock_bin:$PATH" OMI_TEST_DMG_APP_SOURCE="$wrong_firebase_beta" \
  "$SMOKE" --app "$wrong_firebase_beta" --tag v0.12.34+12034-macos \
  --expected-bundle-id com.omi.computer-macos.beta \
  --expected-feed-url 'https://api.omi.me/v2/desktop/appcast.xml?identity=beta' \
  --expected-python-api-url https://api.omiapi.com/ \
  --expected-desktop-api-url https://desktop-backend-dt5lrfkkoa-uc.a.run.app/ \
  >/tmp/omi-smoke-beta-wrong-firebase.out 2>/tmp/omi-smoke-beta-wrong-firebase.err; then
  fail "beta smoke must reject a non-production Firebase project"
fi
grep -q "Firebase project must be based-hardware" /tmp/omi-smoke-beta-wrong-firebase.err \
  || fail "Firebase project rejection should be explicit"

# A signed artifact whose pi-mono-extension is present but empty passed the old
# directory-exists check and still failed every chat turn (pi-mono exits 1 on
# `Unknown provider "omi"`). The release lane must reject it before publication.
mkdir -p "$tmp_root/hollow-runtime"
hollow_runtime_app="$tmp_root/hollow-runtime/Omi.app"
cp -R "$canonical_dmg_app" "$hollow_runtime_app"
rm -f "$hollow_runtime_app/Contents/Resources/pi-mono-extension/index.ts"
if PATH="$mock_bin:$PATH" OMI_TEST_DMG_APP_SOURCE="$hollow_runtime_app" \
  "$SMOKE" --app "$hollow_runtime_app" --tag v0.12.34+12034-macos \
  >/tmp/omi-smoke-hollow-runtime.out 2>/tmp/omi-smoke-hollow-runtime.err; then
  fail "smoke must reject an artifact whose agent runtime payload is incomplete"
fi
grep -q "agent runtime payload incomplete" /tmp/omi-smoke-hollow-runtime.err \
  || fail "incomplete runtime payload rejection should name the contract"
grep -q "pi-mono-extension/index.ts" /tmp/omi-smoke-hollow-runtime.err \
  || fail "incomplete runtime payload rejection should name the missing component"

mkdir -p "$tmp_root/missing-tool-manifest"
missing_tool_manifest_app="$tmp_root/missing-tool-manifest/Omi.app"
cp -R "$canonical_dmg_app" "$missing_tool_manifest_app"
rm -f "$missing_tool_manifest_app/Contents/Resources/agent/dist/runtime/omi-tool-manifest.js"
if PATH="$mock_bin:$PATH" OMI_TEST_DMG_APP_SOURCE="$missing_tool_manifest_app" \
  "$SMOKE" --app "$missing_tool_manifest_app" --tag v0.12.34+12034-macos \
  >/tmp/omi-smoke-missing-tool-manifest.out 2>/tmp/omi-smoke-missing-tool-manifest.err; then
  fail "smoke must reject an artifact whose compiled agent tool manifest is missing"
fi
grep -q "agent/dist/runtime/omi-tool-manifest.js" /tmp/omi-smoke-missing-tool-manifest.err \
  || fail "compiled tool manifest rejection should name the missing component"

# Regression (v0.12.91 build failure): macOS mktemp creates the LITERAL template
# file when characters follow the final XXXXXX, so the second smoke invocation
# in one build (stable then Omi Beta) dies with "File exists". Every template
# must end with XXXXXX.
if grep -nE 'mktemp (-d )?"[^"]*XXXXXX[^"]+"' "$SMOKE"; then
  fail "mktemp template with a suffix after XXXXXX breaks repeat smoke invocations"
fi

echo "signed artifact smoke tests passed"
