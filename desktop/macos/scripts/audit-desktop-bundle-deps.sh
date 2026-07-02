#!/usr/bin/env bash

set -euo pipefail

APP_BUNDLE="${1:-}"

usage() {
  cat <<'USAGE'
Usage: scripts/audit-desktop-bundle-deps.sh /path/to/Omi.app

Audits Mach-O load commands in a desktop app bundle. The audit fails when a
bundled executable or dylib references developer-machine paths such as
/opt/homebrew, /usr/local, or /Users/... instead of system libraries or files
inside the app bundle.
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

if ! command -v otool >/dev/null 2>&1; then
  echo "ERROR: otool is required for bundle dependency audit" >&2
  exit 1
fi

if ! command -v file >/dev/null 2>&1; then
  echo "ERROR: file is required for bundle dependency audit" >&2
  exit 1
fi

APP_BUNDLE="$(cd "$APP_BUNDLE" && pwd)"
CONTENTS_DIR="$APP_BUNDLE/Contents"
EXECUTABLE_DIR="$CONTENTS_DIR/MacOS"
FRAMEWORKS_DIR="$CONTENTS_DIR/Frameworks"
errors=0
checked=0
candidate_rpaths=()

report_error() {
  echo "ERROR: $*" >&2
  errors=$((errors + 1))
}

is_macho() {
  file "$1" 2>/dev/null | grep -q "Mach-O"
}

dependency_exists_in_bundle() {
  local name="$1"
  local root
  local roots=(
    "$FRAMEWORKS_DIR"
    "$EXECUTABLE_DIR"
    "$CONTENTS_DIR/Resources"
    "$CONTENTS_DIR/Resources/Omi Computer_Omi Computer.bundle"
    "$CONTENTS_DIR/Resources/agent"
    "$CONTENTS_DIR/Resources/pi-mono-extension"
  )

  for root in "${roots[@]}"; do
    [[ -e "$root/$name" ]] && return 0
  done

  return 1
}

path_inside_bundle() {
  local path="$1"
  local dir
  local abs

  [[ -e "$path" ]] || return 1
  dir="$(cd "$(dirname "$path")" && pwd)"
  abs="$dir/$(basename "$path")"

  [[ "$abs" == "$APP_BUNDLE"/* ]]
}

resolve_token_path() {
  local token="$1"
  local binary="$2"
  local loader_dir
  loader_dir="$(dirname "$binary")"

  case "$token" in
    @executable_path/*)
      printf '%s/%s\n' "$EXECUTABLE_DIR" "${token#@executable_path/}"
      ;;
    @loader_path/*)
      printf '%s/%s\n' "$loader_dir" "${token#@loader_path/}"
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_rpath_dependency() {
  local binary="$1"
  local dep="$2"
  local dep_name="${dep#@rpath/}"
  local rpath
  local resolved_rpath
  local resolved_dep

  for rpath in "${candidate_rpaths[@]}"; do
    case "$rpath" in
      @executable_path/*|@loader_path/*)
        resolved_rpath="$(resolve_token_path "$rpath" "$binary")" || continue
        ;;
      "$APP_BUNDLE"/*)
        resolved_rpath="$rpath"
        ;;
      /*)
        continue
        ;;
      *)
        continue
        ;;
    esac

    resolved_dep="$resolved_rpath/$dep_name"
    path_inside_bundle "$resolved_dep" && return 0
  done

  dependency_exists_in_bundle "$dep_name"
}

audit_dependency() {
  local binary="$1"
  local dep="$2"
  local resolved

  case "$dep" in
    /System/Library/*|/usr/lib/*)
      return
      ;;
    "$APP_BUNDLE"/*)
      [[ -e "$dep" ]] || report_error "$binary references missing bundle dependency: $dep"
      return
      ;;
    /opt/homebrew/*|/usr/local/*|/Users/*|/private/var/*|/var/folders/*|/tmp/*|/private/tmp/*)
      report_error "$binary references host-local dependency: $dep"
      return
      ;;
    /*)
      report_error "$binary references non-system absolute dependency: $dep"
      return
      ;;
    @rpath/*)
      resolve_rpath_dependency "$binary" "$dep" || report_error "$binary has unresolved bundle @rpath dependency: $dep"
      return
      ;;
    @executable_path/*|@loader_path/*)
      resolved="$(resolve_token_path "$dep" "$binary")"
      [[ -e "$resolved" ]] || report_error "$binary references missing relative dependency: $dep -> $resolved"
      return
      ;;
    *)
      report_error "$binary references unsupported dependency token: $dep"
      return
      ;;
  esac
}

macho_load_command_names() {
  local binary="$1"
  local command_field="$2"
  local name_field="$3"
  local values

  values="$(
    otool -l "$binary" 2>/dev/null | awk -v command_field="$command_field" -v name_field="$name_field" '
    $1 == "cmd" {
      in_target = ($2 == command_field)
      next
    }
    in_target && $1 == name_field {
      sub("^[[:space:]]*" name_field "[[:space:]]+", "")
      sub(/[[:space:]]+\(offset [0-9]+\)$/, "")
      print
      in_target = 0
    }
  '
  )" || return 1

  printf '%s\n' "$values" | sort -u
}

macho_load_dependencies() {
  {
    macho_load_command_names "$1" LC_LOAD_DYLIB name
    macho_load_command_names "$1" LC_LOAD_WEAK_DYLIB name
    macho_load_command_names "$1" LC_REEXPORT_DYLIB name
    macho_load_command_names "$1" LC_LAZY_LOAD_DYLIB name
    macho_load_command_names "$1" LC_LOAD_UPWARD_DYLIB name
  } | sort -u
}

macho_rpaths() {
  macho_load_command_names "$1" LC_RPATH path
}

while IFS= read -r -d '' candidate; do
  if ! is_macho "$candidate"; then
    continue
  fi

  checked=$((checked + 1))
  candidate_rpaths=()
  while IFS= read -r rpath; do
    [[ -n "$rpath" ]] || continue
    candidate_rpaths+=("$rpath")
  done < <(macho_rpaths "$candidate")

  while IFS= read -r dep; do
    [[ -n "$dep" ]] || continue
    audit_dependency "$candidate" "$dep"
  done < <(macho_load_dependencies "$candidate")
done < <(
  find "$CONTENTS_DIR" -type f \
    \( -path "$CONTENTS_DIR/MacOS/*" -o -name '*.node' -o -name '*.dylib' -o -name '*.jnilib' -o -name '*.so' -o -name 'rg' -o -name 'node' -o -name 'ffmpeg' \) \
    -print0
)

node_bin="$CONTENTS_DIR/Resources/Omi Computer_Omi Computer.bundle/node"
if [[ -x "$node_bin" ]]; then
  "$node_bin" --version >/dev/null 2>&1 || report_error "bundled node failed runtime probe: $node_bin"
  codesign --verify --verbose=1 "$node_bin" >/dev/null 2>&1 || report_error "bundled node failed codesign verification: $node_bin"
else
  report_error "bundled node is missing or not executable: $node_bin"
fi

codesign --verify --verbose=1 "$APP_BUNDLE" >/dev/null 2>&1 || report_error "app bundle failed codesign verification: $APP_BUNDLE"

if [[ "$errors" -gt 0 ]]; then
  echo "Desktop bundle dependency audit failed: $errors issue(s), $checked Mach-O file(s) checked" >&2
  exit 1
fi

echo "Desktop bundle dependency audit passed: $checked Mach-O file(s) checked"
