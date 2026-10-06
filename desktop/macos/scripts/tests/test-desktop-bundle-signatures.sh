#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-signature-test.XXXXXX")"
trap 'rm -rf "$temp_dir"' EXIT
app="$temp_dir/Omi.app"
ffmpeg="$app/Contents/Resources/Omi Computer_Omi Computer.bundle/Contents/Resources/ffmpeg"
mkdir -p "$(dirname "$ffmpeg")"
printf 'int main(void) { return 0; }\n' > "$temp_dir/main.c"
clang "$temp_dir/main.c" -o "$ffmpeg"
codesign --remove-signature "$ffmpeg" >/dev/null 2>&1 || true

if "$SCRIPT_DIR/check-desktop-bundle-signatures.sh" --allow-adhoc "$app" >"$temp_dir/check.log" 2>&1; then
  echo "ERROR: unsigned structured-bundle ffmpeg passed signature check" >&2
  exit 1
fi
grep -q 'ffmpeg' "$temp_dir/check.log"

codesign --force --sign - --options runtime "$ffmpeg"
"$SCRIPT_DIR/check-desktop-bundle-signatures.sh" --allow-adhoc "$app"
helper="$app/Contents/Resources/Omi Computer_Omi Computer.bundle/helper"
clang "$temp_dir/main.c" -o "$helper"
codesign --remove-signature "$helper" >/dev/null 2>&1 || true
if "$SCRIPT_DIR/check-desktop-bundle-signatures.sh" --allow-adhoc "$app" >"$temp_dir/check.log" 2>&1; then
  echo "ERROR: unsigned Mach-O with an unfamiliar name passed signature check" >&2
  exit 1
fi
grep -q 'helper' "$temp_dir/check.log"
codesign --force --sign - "$helper"
if "$SCRIPT_DIR/check-desktop-bundle-signatures.sh" --allow-adhoc "$app" >"$temp_dir/check.log" 2>&1; then
  echo "ERROR: Mach-O without hardened runtime passed signature check" >&2
  exit 1
fi
grep -q 'hardened runtime' "$temp_dir/check.log"
codesign --force --sign - --options runtime "$helper"
"$SCRIPT_DIR/check-desktop-bundle-signatures.sh" --allow-adhoc "$app"
if "$SCRIPT_DIR/check-desktop-bundle-signatures.sh" "$app" >"$temp_dir/check.log" 2>&1; then
  echo "ERROR: ad-hoc signature passed release signature check" >&2
  exit 1
fi
grep -q 'ad-hoc\|Developer ID' "$temp_dir/check.log"
echo "Desktop bundle signature check tests passed"
