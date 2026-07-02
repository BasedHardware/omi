#!/usr/bin/env bash

set -euo pipefail

APP_BUNDLE="${1:-}"

usage() {
  cat <<'USAGE'
Usage: scripts/prepare-desktop-bundle-native-deps.sh /path/to/Omi.app

Normalizes bundled native Node dependencies before signing:
  - rewrites host-machine LC_ID_DYLIB values in .node dylibs
  - vendors Homebrew pcre2 next to bundled ripgrep binaries that need it
USAGE
}

if [[ -z "$APP_BUNDLE" || "$APP_BUNDLE" == "--help" || "$APP_BUNDLE" == "-h" ]]; then
  usage
  [[ -n "$APP_BUNDLE" ]] && exit 0
  exit 2
fi

if [[ ! -d "$APP_BUNDLE/Contents" ]]; then
  echo "ERROR: app bundle not found: $APP_BUNDLE" >&2
  exit 1
fi

APP_BUNDLE="$(cd "$APP_BUNDLE" && pwd)"
CONTENTS_DIR="$APP_BUNDLE/Contents"

is_macho() {
  file "$1" 2>/dev/null | grep -q "Mach-O"
}

host_local_id_names() {
  otool -l "$1" 2>/dev/null | awk '
    $1 == "cmd" && $2 == "LC_ID_DYLIB" { in_id = 1; next }
    $1 == "cmd" { in_id = 0; next }
    in_id && $1 == "name" {
      print $2
      in_id = 0
    }
  ' | grep -E '^(/Users/|/private/var/|/var/folders/|/tmp/|/private/tmp/)' || true
}

normalize_install_ids() {
  local candidate="$1"
  local bad_id

  while IFS= read -r bad_id; do
    [[ -n "$bad_id" ]] || continue
    install_name_tool -id "@rpath/$(basename "$candidate")" "$candidate"
  done < <(host_local_id_names "$candidate")
}

find_pcre2() {
  local pcre2
  for pcre2 in \
    /opt/homebrew/opt/pcre2/lib/libpcre2-8.0.dylib \
    /opt/homebrew/lib/libpcre2-8.0.dylib \
    /usr/local/opt/pcre2/lib/libpcre2-8.0.dylib \
    /usr/local/lib/libpcre2-8.0.dylib; do
    if [[ -f "$pcre2" ]]; then
      printf '%s\n' "$pcre2"
      return 0
    fi
  done
  return 1
}

vendor_pcre2_for_ripgrep() {
  local rg="$1"
  local dep
  local pcre2
  local dest

  while IFS= read -r dep; do
    [[ -n "$dep" ]] || continue
    if ! pcre2="$(find_pcre2)"; then
      echo "ERROR: $rg depends on $dep but libpcre2-8.0.dylib was not found" >&2
      exit 1
    fi

    dest="$(dirname "$rg")/libpcre2-8.0.dylib"
    cp -f "$pcre2" "$dest"
    chmod u+w "$dest"
    install_name_tool -id "@rpath/libpcre2-8.0.dylib" "$dest"
    install_name_tool -change "$dep" "@loader_path/libpcre2-8.0.dylib" "$rg"
  done < <(
    otool -L "$rg" 2>/dev/null | awk '
      /^\t/ {
        sub(/^[ \t]+/, "")
        sub(/ \(.*$/, "")
        print
      }
    ' | grep -E '^(/opt/homebrew|/usr/local)/.*libpcre2-8\.0\.dylib$' || true
  )
}

while IFS= read -r -d '' candidate; do
  is_macho "$candidate" || continue
  chmod u+w "$candidate" 2>/dev/null || true
  normalize_install_ids "$candidate"
done < <(
  find "$CONTENTS_DIR/Resources" -type f \
    \( -name '*.node' -o -name '*.dylib' -o -name '*.jnilib' -o -name '*.so' -o -name 'rg' -o -name 'node' -o -name 'ffmpeg' \) \
    -print0 2>/dev/null
)

while IFS= read -r -d '' rg; do
  is_macho "$rg" || continue
  chmod u+w "$rg" 2>/dev/null || true
  vendor_pcre2_for_ripgrep "$rg"
done < <(find "$CONTENTS_DIR/Resources" -path '*/vendor/ripgrep/*-darwin/rg' -type f -print0 2>/dev/null)

echo "Prepared desktop bundle native dependencies"
