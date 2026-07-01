#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HARNESS="$MACOS_DIR/scripts/omi-harness"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

cat >"$TMPDIR/yaml.py" <<'PY'
def safe_load(handle):
    data = {}
    for raw_line in handle.read().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value == "[]":
            parsed = []
        else:
            try:
                parsed = int(value)
            except ValueError:
                parsed = value
        data[key.strip()] = parsed
    return data
PY
export PYTHONPATH="$TMPDIR${PYTHONPATH:+:$PYTHONPATH}"

write_flow() {
  local path="$1" version="$2"
  cat >"$path" <<YAML
version: $version
name: schema-$version
steps: []
YAML
}

write_flow "$TMPDIR/future.yaml" 3
if "$HARNESS" run "$TMPDIR/future.yaml" --out "$TMPDIR/runs" >"$TMPDIR/future.out" 2>"$TMPDIR/future.err"; then
  fail "future schema unexpectedly succeeded"
fi
if ! grep -q "newer than supported version 2" "$TMPDIR/future.err"; then
  fail "future schema error did not mention supported version"
fi

write_flow "$TMPDIR/legacy.yaml" 1
if "$HARNESS" run "$TMPDIR/legacy.yaml" --out "$TMPDIR/runs" >"$TMPDIR/legacy.out" 2>"$TMPDIR/legacy.err"; then
  fail "legacy schema unexpectedly succeeded without explicit compatibility"
fi
if ! grep -q "requires explicit compatibility" "$TMPDIR/legacy.err"; then
  fail "legacy schema error did not mention explicit compatibility"
fi

if "$HARNESS" run "$TMPDIR/legacy.yaml" --allow-legacy-flow-version --out "$TMPDIR/runs" \
    --port 9 >"$TMPDIR/legacy-opt-in.out" 2>"$TMPDIR/legacy-opt-in.err"; then
  fail "legacy opt-in unexpectedly passed against closed bridge port"
fi
if grep -q "requires explicit compatibility" "$TMPDIR/legacy-opt-in.err"; then
  fail "legacy opt-in was still rejected by schema compatibility gate"
fi

echo "omi-harness schema tests passed"
