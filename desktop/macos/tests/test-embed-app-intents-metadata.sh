#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGER="$SCRIPT_DIR/../scripts/embed-app-intents-metadata.sh"
FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

mkdir -p "$FIXTURE/Desktop/.build" "$FIXTURE/Omi.app/Contents/Resources" "$FIXTURE/bin"
cat > "$FIXTURE/package.json" <<'JSON'
{"targets":[{"name":"Omi Computer","sources":[]}]}
JSON
cat > "$FIXTURE/bin/xcrun" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-} ${2:-}" = 'swift package' ]]; then
  cat "$SIRI_TEST_PACKAGE_DESCRIPTION"
else
  echo "unexpected xcrun invocation: $*" >&2
  exit 99
fi
SH
chmod +x "$FIXTURE/bin/xcrun"
export PATH="$FIXTURE/bin:$PATH"
export SIRI_TEST_PACKAGE_DESCRIPTION="$FIXTURE/package.json"

"$PACKAGER" "$FIXTURE/Desktop" "$FIXTURE/Omi.app" Release arm64 --expect-absent > "$FIXTURE/absent.out" 2>&1 || {
  cat "$FIXTURE/absent.out" >&2
  echo 'FAIL: stable metadata check must work without constant-value files' >&2
  exit 1
}
grep -Fq 'Xcode 26.6 bundle has no Metadata.appintents' "$FIXTURE/absent.out" || {
  echo 'FAIL: stable metadata check did not prove bundle absence' >&2
  exit 1
}

if "$PACKAGER" "$FIXTURE/Desktop" "$FIXTURE/Omi.app" Release arm64 --require-siri > "$FIXTURE/required.out" 2>&1; then
  echo 'FAIL: Siri metadata packaging accepted missing constant-value files' >&2
  exit 1
fi
grep -Fq 'Omi Computer constant-value files missing; build with -Xswiftc -emit-const-values' "$FIXTURE/required.out" || {
  cat "$FIXTURE/required.out" >&2
  echo 'FAIL: Siri metadata packaging gave no missing-constants diagnostic' >&2
  exit 1
}

echo 'metadata packager stable and Siri modes handle missing constant values'
