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

write_flow() {
  local path="$1" version="$2"
  cat >"$path" <<YAML
version: $version
name: schema-$version
steps: []
YAML
}

write_flow "$TMPDIR/future.yaml" 3
if "$HARNESS" run "$TMPDIR/future.yaml" --out "$TMPDIR/runs" >/tmp/omi-harness-future.out 2>/tmp/omi-harness-future.err; then
  fail "future schema unexpectedly succeeded"
fi
if ! grep -q "newer than supported version 2" /tmp/omi-harness-future.err; then
  fail "future schema error did not mention supported version"
fi

write_flow "$TMPDIR/legacy.yaml" 1
if "$HARNESS" run "$TMPDIR/legacy.yaml" --out "$TMPDIR/runs" >/tmp/omi-harness-legacy.out 2>/tmp/omi-harness-legacy.err; then
  fail "legacy schema unexpectedly succeeded without explicit compatibility"
fi
if ! grep -q "requires explicit compatibility" /tmp/omi-harness-legacy.err; then
  fail "legacy schema error did not mention explicit compatibility"
fi

if "$HARNESS" run "$TMPDIR/legacy.yaml" --allow-legacy-flow-version --out "$TMPDIR/runs" \
    --port 9 >/tmp/omi-harness-legacy-opt-in.out 2>/tmp/omi-harness-legacy-opt-in.err; then
  fail "legacy opt-in unexpectedly passed against closed bridge port"
fi
if grep -q "requires explicit compatibility" /tmp/omi-harness-legacy-opt-in.err; then
  fail "legacy opt-in was still rejected by schema compatibility gate"
fi

echo "omi-harness schema tests passed"
