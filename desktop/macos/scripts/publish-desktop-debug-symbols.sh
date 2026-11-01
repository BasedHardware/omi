#!/usr/bin/env bash
# Build and verify the exact dSYM for the final universal desktop executable.
#
# The verified dSYM is retained as a GitHub release artifact so crash reports
# can be symbolicated offline. There is no symbol-upload destination anymore:
# the previous Sentry dSYM upload path was removed together with Sentry itself.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  publish-desktop-debug-symbols.sh generate --binary <Mach-O> --dsym <output.dSYM> --archive <output.zip>
EOF
  exit 2
}

[[ $# -ge 1 ]] || usage
mode="$1"
shift

binary=""
dsym=""
archive=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --binary) binary="$2"; shift 2 ;;
    --dsym) dsym="$2"; shift 2 ;;
    --archive) archive="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "$binary" && -n "$dsym" ]] || usage
[[ -f "$binary" ]] || { echo "ERROR: desktop executable not found: $binary" >&2; exit 1; }
[[ "$dsym" == *.dSYM && "$dsym" != "/" ]] || {
  echo "ERROR: dSYM output must be a specific .dSYM path" >&2
  exit 1
}

uuid_set() {
  xcrun dwarfdump --uuid "$1" \
    | awk '/^UUID:/ {print toupper($2) " " $3}' \
    | sort -u
}

verify_symbols() {
  [[ -d "$dsym" ]] || { echo "ERROR: dSYM bundle not found: $dsym" >&2; exit 1; }
  local binary_uuids dsym_uuids
  binary_uuids="$(uuid_set "$binary")"
  dsym_uuids="$(uuid_set "$dsym")"
  [[ -n "$binary_uuids" ]] || { echo "ERROR: executable has no Mach-O UUIDs" >&2; exit 1; }
  if [[ "$binary_uuids" != "$dsym_uuids" ]]; then
    echo "ERROR: dSYM UUIDs do not exactly match the release executable" >&2
    echo "Executable UUIDs:" >&2
    printf '%s\n' "$binary_uuids" >&2
    echo "dSYM UUIDs:" >&2
    printf '%s\n' "$dsym_uuids" >&2
    exit 1
  fi
  printf 'Verified desktop dSYM UUIDs:\n%s\n' "$dsym_uuids"
}

case "$mode" in
  generate)
    [[ -n "$archive" && "$archive" == *.zip ]] || usage
    [[ ! -e "$dsym" ]] || { echo "ERROR: refusing to overwrite existing dSYM: $dsym" >&2; exit 1; }
    [[ ! -e "$archive" ]] || { echo "ERROR: refusing to overwrite existing archive: $archive" >&2; exit 1; }
    xcrun dsymutil "$binary" -o "$dsym"
    verify_symbols
    ditto -c -k --keepParent "$dsym" "$archive"
    [[ -s "$archive" ]] || { echo "ERROR: dSYM archive was not created" >&2; exit 1; }
    echo "Created desktop debug-symbol archive: $archive"
    ;;
  *)
    usage
    ;;
esac
