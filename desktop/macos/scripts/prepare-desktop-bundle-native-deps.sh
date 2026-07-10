#!/usr/bin/env bash

set -euo pipefail

APP_BUNDLE="${1:-}"

usage() {
  cat <<'USAGE'
Usage: scripts/prepare-desktop-bundle-native-deps.sh /path/to/Omi.app

Normalizes bundled native Node dependencies before signing:
  - rewrites host-machine LC_ID_DYLIB values in .node dylibs
  - vendors Homebrew pcre2 next to bundled ripgrep binaries that need it
  - strips local symbols from the main app executable before codesign
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
MACOS_DIR="$CONTENTS_DIR/MacOS"

human_bytes() {
  local bytes="$1"
  awk -v bytes="$bytes" 'BEGIN {
    split("B KiB MiB GiB", units, " ")
    value = bytes + 0
    unit = 1
    while (value >= 1024 && unit < 4) {
      value = value / 1024
      unit++
    }
    if (unit == 1) {
      printf "%d %s", value, units[unit]
    } else {
      printf "%.1f %s", value, units[unit]
    }
  }'
}

file_size_bytes() {
  if stat -f%z "$1" >/dev/null 2>&1; then
    stat -f%z "$1"
  else
    stat -c%s "$1"
  fi
}

main_executable_name() {
  local executable
  local candidate

  executable="$(/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" "$CONTENTS_DIR/Info.plist" 2>/dev/null || true)"
  if [[ -n "$executable" && -f "$MACOS_DIR/$executable" ]]; then
    printf '%s\n' "$executable"
    return 0
  fi

  while IFS= read -r -d '' candidate; do
    if [[ -f "$candidate" && -x "$candidate" ]]; then
      basename "$candidate"
      return 0
    fi
  done < <(find "$MACOS_DIR" -maxdepth 1 -type f -print0 2>/dev/null)
}

is_macho() {
  file "$1" 2>/dev/null | grep -q "Mach-O"
}

macho_arches() {
  file "$1" 2>/dev/null | grep -oE 'arm64|x86_64' | sort -u | tr '\n' ' '
}

strip_main_executable() {
  if [[ "${OMI_SKIP_MAIN_BINARY_STRIP:-0}" == "1" ]]; then
    echo "Skipping main app executable strip (OMI_SKIP_MAIN_BINARY_STRIP=1)"
    return 0
  fi

  if ! command -v strip >/dev/null 2>&1; then
    echo "WARNING: strip not found; leaving main app executable unstripped" >&2
    return 0
  fi

  local executable_name
  local executable_path
  local before_bytes
  local after_bytes
  local before_arches
  local after_arches
  local saved_bytes

  executable_name="$(main_executable_name || true)"
  if [[ -z "$executable_name" ]]; then
    echo "WARNING: could not determine main app executable; skipping strip" >&2
    return 0
  fi

  executable_path="$MACOS_DIR/$executable_name"
  if [[ ! -f "$executable_path" ]]; then
    echo "WARNING: main app executable missing at $executable_path; skipping strip" >&2
    return 0
  fi
  if ! is_macho "$executable_path"; then
    echo "WARNING: main app executable is not Mach-O: $executable_path; skipping strip" >&2
    return 0
  fi

  before_bytes="$(file_size_bytes "$executable_path")"
  before_arches="$(macho_arches "$executable_path")"
  chmod u+w "$executable_path" 2>/dev/null || true
  strip -x "$executable_path"
  after_bytes="$(file_size_bytes "$executable_path")"
  after_arches="$(macho_arches "$executable_path")"

  if [[ "$before_arches" != "$after_arches" ]]; then
    echo "ERROR: strip changed main executable architectures: before='$before_arches' after='$after_arches'" >&2
    exit 1
  fi
  if [[ "$after_bytes" -gt "$before_bytes" ]]; then
    echo "ERROR: strip increased main executable size: $(human_bytes "$before_bytes") -> $(human_bytes "$after_bytes")" >&2
    exit 1
  fi

  saved_bytes=$((before_bytes - after_bytes))
  echo "Stripped main app executable: $(human_bytes "$before_bytes") -> $(human_bytes "$after_bytes") (saved $(human_bytes "$saved_bytes"))"
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

resolve_pcre2_for_dep() {
  local dep="$1"

  if [[ -f "$dep" ]]; then
    printf '%s\n' "$dep"
    return 0
  fi

  find_pcre2
}

vendor_pcre2_for_ripgrep() {
  local rg="$1"
  local dep
  local pcre2
  local dest

  while IFS= read -r dep; do
    [[ -n "$dep" ]] || continue
    if ! pcre2="$(resolve_pcre2_for_dep "$dep")"; then
      echo "ERROR: $rg depends on $dep but neither that file nor a fallback libpcre2-8.0.dylib was found" >&2
      echo "HINT: install Homebrew pcre2 so the Claude SDK ripgrep binary can be vendored into the app bundle:" >&2
      echo "  brew install pcre2" >&2
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

strip_main_executable

echo "Prepared desktop bundle native dependencies"
