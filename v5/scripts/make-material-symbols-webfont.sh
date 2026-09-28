#!/usr/bin/env bash
# Regenerates the PWA's Material Symbols Rounded webfont subset from the
# codepoint table in react-native/src/ui/MaterialIcon.tsx. Run after adding
# glyphs to GLYPHS (requires fonttools: `wax install fonttools`).
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
source_ttf="$repo/react-native/macos/RnRuntime-macOS/Resources/MaterialSymbolsRounded.ttf"
output="$repo/pwa/public/MaterialSymbolsRounded.woff2"
glyphs_ts="$repo/react-native/src/ui/MaterialIcon.tsx"

codes="$(
  grep -oE '0x[0-9a-fA-F]+' "$glyphs_ts" |
    tr 'a-fA-F' 'A-F' |
    sed 's/^0X/U+/' |
    paste -sd, -
)"
if [ -z "$codes" ]; then
  echo "no glyphs found in $glyphs_ts" >&2
  exit 1
fi

pyftsubset "$source_ttf" \
  --output-file="$output" \
  --flavor=woff2 \
  --unicodes="$codes" \
  --layout-features='*'

echo "wrote $output ($(wc -c <"$output" | tr -d ' ') bytes) for $codes"
