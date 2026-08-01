#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/omi-audit-bundle-deps-test.XXXXXX")"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

fakebin="$tmpdir/bin"
app_bundle="$tmpdir/Omi Test.app"
main_binary="$app_bundle/Contents/MacOS/Omi Computer"
node_bin="$app_bundle/Contents/Resources/Omi Computer_Omi Computer.bundle/Contents/Resources/node"
framework="$app_bundle/Contents/Frameworks/libexample.dylib"
mkdir -p "$fakebin" "$(dirname "$main_binary")" "$(dirname "$node_bin")" "$(dirname "$framework")"
touch "$main_binary" "$node_bin" "$framework"
chmod +x "$main_binary" "$node_bin"

cat > "$fakebin/file" <<'EOF'
#!/usr/bin/env bash
echo "$1: Mach-O 64-bit executable arm64"
EOF
chmod +x "$fakebin/file"

cat > "$fakebin/otool" <<'EOF'
#!/usr/bin/env bash
cat <<'OUTPUT'
Load command 0
          cmd LC_LOAD_DYLIB
      cmdsize 56
         name @rpath/libexample.dylib (offset 24)
OUTPUT
EOF
chmod +x "$fakebin/otool"

cat > "$fakebin/codesign" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$fakebin/codesign"

output="$(PATH="$fakebin:$PATH" "$MACOS_DIR/scripts/audit-desktop-bundle-deps.sh" "$app_bundle")"

if ! grep -q "Desktop bundle dependency audit passed" <<< "$output"; then
  fail "audit did not complete successfully with an empty rpath list"
fi

echo "audit-desktop-bundle-deps tests passed"
