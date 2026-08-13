#!/usr/bin/env bash
#
# Behavioral tests for detect_apple_team_id() in app/setup.sh.
#
# These drive the real function through two seams — $HOME (where it looks for
# provisioning profiles) and stdin (whether a human is attached) — rather than
# asserting on the source text.
#
# Regression covered: with no detectable team and no TTY, the function used to
# block forever on `read`, hanging setup.sh in CI and nested automation. It must
# fail fast with a non-zero status instead.

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

# Extract the helper functions under test into a standalone harness, so we don't
# execute setup.sh's top-level body (which prints banners and expects args).
HARNESS="$(mktemp -t omi_detect_team_XXXXXX)"
trap 'rm -f "$HARNESS"' EXIT

extract_function() {
  # Prints from "function <name>()" through the first line that is exactly "}".
  awk -v fn="function $1()" '
    index($0, fn) == 1 { capture = 1 }
    capture { print }
    capture && $0 == "}" { exit }
  ' "$SETUP_SH"
}

{
  echo "set -uo pipefail"
  extract_function generate_device_suffix
  extract_function detect_apple_team_id
} > "$HARNESS"

if ! bash -n "$HARNESS"; then
  echo "FAIL: extracted harness is not valid bash" >&2
  exit 1
fi

# Run a command with a deadline, without depending on GNU `timeout` being
# present. Exits 124 if the deadline is hit, mirroring timeout(1).
run_with_deadline() {
  local deadline="$1"; shift
  local rc=0
  ( "$@" ) & local pid=$!
  ( sleep "$deadline"; kill -9 "$pid" 2>/dev/null ) & local killer=$!
  wait "$pid" 2>/dev/null || rc=$?
  kill "$killer" 2>/dev/null
  wait "$killer" 2>/dev/null || true
  # 137 == SIGKILL from the deadline watchdog
  if [[ "$rc" -eq 137 ]]; then return 124; fi
  return "$rc"
}

echo "detect_apple_team_id:"

# ---------------------------------------------------------------------------
# 1. An explicit APPLE_DEVELOPMENT_TEAM override wins, with no filesystem or
#    keychain access at all.
# ---------------------------------------------------------------------------
got="$(APPLE_DEVELOPMENT_TEAM=ABCDE12345 bash -c "source '$HARNESS'; detect_apple_team_id" 2>/dev/null)"
if [[ "$got" == "ABCDE12345" ]]; then
  pass "honours APPLE_DEVELOPMENT_TEAM override"
else
  fail "expected override 'ABCDE12345', got '${got}'"
fi

# ---------------------------------------------------------------------------
# 2. No override, no discoverable profiles, no TTY -> must fail fast rather than
#    block on read. An empty $HOME guarantees the profile scan finds nothing.
# ---------------------------------------------------------------------------
empty_home="$(mktemp -d -t omi_empty_home_XXXXXX)"
rc=0
run_with_deadline 20 env -u APPLE_DEVELOPMENT_TEAM HOME="$empty_home" \
  bash -c "source '$HARNESS'; detect_apple_team_id < /dev/null" >/dev/null 2>&1 || rc=$?
rm -rf "$empty_home"

case "$rc" in
  124) fail "hung waiting for input with no TTY (the regression)" ;;
  0)   fail "reported success despite having no team to detect" ;;
  *)   pass "fails fast (rc=$rc) instead of blocking on read without a TTY" ;;
esac

# ---------------------------------------------------------------------------
# Candidate filtering (step 3). Fixtures generate real certificates with openssl,
# so a profile's embedded certificate and the stubbed identity list agree on a
# genuine SHA-1 fingerprint.
#
# Regression covered: the filter used to decide which team a certificate belonged
# to by reading the team out of the certificate's common name. That is not
# authoritative — Apple keeps the original personal-team ID in the common name
# when a developer joins a paid team, so a certificate reading
# "Apple Development: NAME (PERSONALTEAM)" can be issued under a different team.
# The name-based check therefore rejected teams the developer could sign for. It
# also matched as a bare substring, so a hex-only team ID could match inside the
# 40-char SHA-1 that begins every identity line. The check is now the one Xcode
# makes: does the profile embed a certificate whose private key we hold?
# ---------------------------------------------------------------------------

# Generates a self-signed certificate, echoing "<base64-DER> <SHA1-FINGERPRINT>".
# The common name deliberately carries a DIFFERENT team than the profile's, which
# is the real-world shape the old check got wrong.
make_cert() {
  local dir="$1" cn="$2"
  openssl req -x509 -newkey rsa:2048 -keyout "$dir/k.pem" -out "$dir/c.pem" \
    -days 1 -nodes -subj "/CN=$cn" >/dev/null 2>&1
  openssl x509 -in "$dir/c.pem" -outform DER -out "$dir/c.der" 2>/dev/null
  local fp
  fp=$(openssl x509 -in "$dir/c.der" -inform DER -noout -fingerprint -sha1 2>/dev/null \
    | sed 's/.*=//; s/://g' | tr '[:lower:]' '[:upper:]')
  printf '%s %s\n' "$(base64 < "$dir/c.der" | tr -d '\n')" "$fp"
}

# Builds a fake $HOME with one profile per team, plus a `security` stub on PATH.
# Each profile embeds $embedded_b64; $identities is the stubbed find-identity text.
make_profile_fixture() {
  local root="$1" embedded_b64="$2" identities="$3"; shift 3
  local profiles="$root/home/Library/Developer/Xcode/UserData/Provisioning Profiles"
  mkdir -p "$profiles" "$root/bin"
  local i=0
  for team in "$@"; do
    i=$((i + 1))
    : > "$profiles/p$i.mobileprovision"
    cat > "$profiles/p$i.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>application-identifier</key>
  <string>${team}.com.example.not-this-machine</string>
  <key>TeamIdentifier</key>
  <array><string>${team}</string></array>
  <key>DeveloperCertificates</key>
  <array><data>${embedded_b64}</data></array>
</dict>
</plist>
PLIST
  done
  printf '%s\n' "$identities" > "$root/identities.txt"
  cat > "$root/bin/security" <<'STUB'
#!/usr/bin/env bash
if [ "$1" = "cms" ]; then
  for a in "$@"; do prev=$last; last=$a; done
  cat "${last%.mobileprovision}.plist"; exit 0
fi
if [ "$1" = "find-identity" ]; then cat "$FIXTURE_ROOT/identities.txt"; exit 0; fi
exit 1
STUB
  chmod +x "$root/bin/security"
}

detect_with_fixture() {
  local root="$1"
  FIXTURE_ROOT="$root" PATH="$root/bin:$PATH" HOME="$root/home" \
    env -u APPLE_DEVELOPMENT_TEAM bash -c "source '$HARNESS'; detect_apple_team_id" 2>/dev/null
}

echo "detect_apple_team_id candidate filter:"

# 1. The profile's team is offered when we hold its embedded certificate, even
#    though that certificate's common name names a DIFFERENT team. This is the
#    case the old name-matching check rejected.
root=$(mktemp -d -t omi_sig_a_XXXXXX)
read -r der fp <<<"$(make_cert "$root" "Apple Development: Dev (PERSONALTM)")"
make_profile_fixture "$root" "$der" \
"  1) $fp \"Apple Development: Dev (PERSONALTM)\"
     1 valid identities found" \
  PAIDTEAM01
got=$(detect_with_fixture "$root")
rm -rf "$root"
if [ "$got" = "PAIDTEAM01" ]; then
  pass "offers the profile's team when we hold its embedded cert, despite a differing cert name"
else
  fail "expected PAIDTEAM01 from the profile's TeamIdentifier, got '${got}'"
fi

# 2. A profile whose embedded certificate we do NOT hold must not be offered.
#    Without this the fallback sends developers to teams they cannot sign for.
root=$(mktemp -d -t omi_sig_b_XXXXXX)
read -r der fp <<<"$(make_cert "$root" "Apple Development: Someone Else (OTHERTEAM)")"
make_profile_fixture "$root" "$der" \
'  1) 0000000000000000000000000000000000000000 "Apple Development: Dev (MINETEAM01)"
     1 valid identities found' \
  NOTMYTEAM1
rc=0
detect_with_fixture "$root" >/dev/null 2>&1 || rc=$?
rm -rf "$root"
if [ "$rc" -ne 0 ]; then
  pass "does not offer a team whose embedded cert we do not hold (rc=$rc)"
else
  fail "offered a team despite holding none of its profile's certificates"
fi

# 3. Only iOS development identities count. A machine holding just a Mac
#    "Developer ID Application" certificate cannot sign an iOS development build,
#    so there is nothing to offer even though the fingerprint matches.
root=$(mktemp -d -t omi_sig_c_XXXXXX)
read -r der fp <<<"$(make_cert "$root" "Developer ID Application: Dev (PAIDTEAM01)")"
make_profile_fixture "$root" "$der" \
"  1) $fp \"Developer ID Application: Dev (PAIDTEAM01)\"
     1 valid identities found" \
  PAIDTEAM01
rc=0
detect_with_fixture "$root" >/dev/null 2>&1 || rc=$?
rm -rf "$root"
if [ "$rc" -ne 0 ]; then
  pass "ignores a Mac-only Developer ID identity (rc=$rc)"
else
  fail "accepted a team backed only by a Developer ID Application certificate"
fi

echo

if [[ "$failures" -gt 0 ]]; then
  echo "$failures shell test(s) failed" >&2
  exit 1
fi
echo "all detect_apple_team_id shell tests passed"
