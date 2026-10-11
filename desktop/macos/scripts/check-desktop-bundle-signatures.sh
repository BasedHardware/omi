#!/usr/bin/env bash
set -euo pipefail

allow_adhoc=false
if [[ "${1:-}" == "--allow-adhoc" ]]; then
  allow_adhoc=true
  shift
fi
app="${1:-}"
if [[ -z "$app" || ! -d "$app/Contents" ]]; then
  echo "Usage: $0 [--allow-adhoc] /path/to/Omi.app" >&2
  exit 2
fi

errors=0
checked=0
macho_candidates="$(mktemp "${TMPDIR:-/tmp}/omi-macho-candidates.XXXXXX")"
trap 'rm -f "$macho_candidates"' EXIT
# Opening each file once is much faster than spawning `file` for every JS asset
# in agent/node_modules. Confirm magic matches with `file` below (CAFEBABE can
# also identify a Java class file).
python3 - "$app/Contents" > "$macho_candidates" <<'PY'
import os
import sys

magics = {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
          b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}

def fail(error):
    raise error

for directory, _, filenames in os.walk(sys.argv[1], onerror=fail):
    for filename in filenames:
        candidate = os.path.join(directory, filename)
        if os.path.islink(candidate):
            continue
        with open(candidate, "rb") as handle:
            if handle.read(4) in magics:
                sys.stdout.buffer.write(os.fsencode(candidate) + b"\0")
PY
while IFS= read -r -d '' candidate; do
  if ! file "$candidate" | grep -q 'Mach-O'; then
    continue
  fi
  checked=$((checked + 1))
  if ! codesign --verify --strict "$candidate" >/dev/null 2>&1; then
    echo "ERROR: unsigned or invalid Mach-O: $candidate" >&2
    errors=$((errors + 1))
    continue
  fi
  details="$(codesign -dv --verbose=4 "$candidate" 2>&1)"
  if ! grep -Eq '^CodeDirectory .*flags=.*\([^)]*runtime([,)]|$)' <<< "$details"; then
    echo "ERROR: Mach-O lacks hardened runtime: $candidate" >&2
    errors=$((errors + 1))
  fi
  if [[ "$allow_adhoc" == false ]]; then
    if ! grep -q '^Authority=Developer ID Application:' <<< "$details"; then
      echo "ERROR: Mach-O lacks Developer ID Application signature (ad-hoc or other identity): $candidate" >&2
      errors=$((errors + 1))
    fi
    if ! grep -q '^Timestamp=' <<< "$details"; then
      echo "ERROR: Mach-O lacks secure timestamp: $candidate" >&2
      errors=$((errors + 1))
    fi
  fi
done < "$macho_candidates"

if [[ "$checked" -eq 0 ]]; then
  echo "ERROR: no Mach-O files found in app bundle: $app" >&2
  exit 1
fi
if [[ "$errors" -gt 0 ]]; then
  echo "Desktop bundle signature check failed: $errors issue(s) across $checked Mach-O file(s)" >&2
  exit 1
fi
echo "Desktop bundle signature check passed: $checked Mach-O file(s)"
