#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/omi-prepare-native-deps-test.XXXXXX")"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

fakebin="$tmpdir/bin"
app_bundle="$tmpdir/Omi Test.app"
main_binary="$app_bundle/Contents/MacOS/Omi Computer"
mkdir -p "$fakebin" "$app_bundle/Contents/MacOS" "$app_bundle/Contents/Resources"

cat > "$fakebin/file" <<'EOF'
#!/usr/bin/env bash
for arg in "$@"; do
  case "$arg" in
    *"/Contents/MacOS/Omi Computer")
      echo "$arg: Mach-O universal binary with 2 architectures: [x86_64] [arm64]"
      ;;
    *)
      echo "$arg: ASCII text"
      ;;
  esac
done
EOF
chmod +x "$fakebin/file"

cat > "$fakebin/strip" <<'EOF'
#!/usr/bin/env bash
target="${@: -1}"
before="$(wc -c < "$target" | tr -d ' ')"
after=$((before - 256))
if [ "$after" -lt 1 ]; then
  after=1
fi
perl -e 'truncate $ARGV[0], $ARGV[1] or die "truncate: $!"' "$target" "$after"
EOF
chmod +x "$fakebin/strip"

head -c 4096 /dev/zero > "$main_binary"
chmod +x "$main_binary"

before="$(wc -c < "$main_binary" | tr -d ' ')"
output="$(PATH="$fakebin:$PATH" "$MACOS_DIR/scripts/prepare-desktop-bundle-native-deps.sh" "$app_bundle")"
after="$(wc -c < "$main_binary" | tr -d ' ')"

if [ "$after" -ge "$before" ]; then
  fail "main executable was not stripped: before=$before after=$after"
fi
if ! grep -q "Stripped main app executable:" <<< "$output"; then
  fail "prepare script did not report main executable strip"
fi
if ! grep -q "Prepared desktop bundle native dependencies" <<< "$output"; then
  fail "prepare script did not complete successfully"
fi

echo "prepare-desktop-bundle-native-deps tests passed"
