#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMATTER="$ROOT/scripts/backend-python-format"
WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

STUBS="$WORK/stubs"
mkdir -p "$STUBS"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

make_black_stub() {
  cat > "$STUBS/black" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "--version" ]; then
  echo "black, ${STUB_BLACK_VERSION} (compiled: yes)"
  exit 0
fi
printf '%s\n' "$@" > "$BLACK_LOG"
STUB
  chmod +x "$STUBS/black"
}

make_python_stub() {
  cat > "$STUBS/python3" <<'STUB'
#!/usr/bin/env bash
exit 1
STUB
  chmod +x "$STUBS/python3"
}

make_uvx_stub() {
  cat > "$STUBS/uvx" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "$UVX_LOG"
STUB
  chmod +x "$STUBS/uvx"
}

export BLACK_LOG="$WORK/black.log" UVX_LOG="$WORK/uvx.log"
make_black_stub
make_python_stub
make_uvx_stub

# An exact installed Black is the zero-download fast path.
export STUB_BLACK_VERSION=26.5.1
PATH="$STUBS:/usr/bin:/bin" "$FORMATTER" --write backend/example.py
test ! -e "$UVX_LOG" || fail "exact Black unexpectedly used uvx"
grep -Fxq -- '--line-length' "$BLACK_LOG" || fail "write mode did not pass formatter options"
grep -Fxq -- 'backend/example.py' "$BLACK_LOG" || fail "write mode did not pass the file"

# A suffixed build is not exact and converges through the pinned uvx environment.
rm -f "$BLACK_LOG" "$UVX_LOG"
export STUB_BLACK_VERSION=26.5.1.dev1
PATH="$STUBS:/usr/bin:/bin" "$FORMATTER" --check backend/example.py
test "$(sed -n '1p' "$UVX_LOG")" = "--from" || fail "uvx is missing --from"
test "$(sed -n '2p' "$UVX_LOG")" = "black==26.5.1" || fail "uvx did not receive the pinned Black version"
test "$(sed -n '3p' "$UVX_LOG")" = "black" || fail "uvx did not invoke Black"
grep -Fxq -- '--check' "$UVX_LOG" || fail "check mode did not reach Black"

# Without an exact Black or uvx, fail with one actionable install path.
rm -f "$STUBS/uvx" "$UVX_LOG"
if output="$(PATH="$STUBS:/usr/bin:/bin" "$FORMATTER" --check backend/example.py 2>&1)"; then
  fail "missing formatter prerequisites unexpectedly passed"
fi
case "$output" in
  *"https://docs.astral.sh/uv/getting-started/installation/"*) ;;
  *) fail "missing formatter error did not point to the uv install path" ;;
esac

# The pin lives only in the shared primitive; all callers delegate to it.
for caller in scripts/pre-commit scripts/pre-push .github/workflows/repo-checks.yml; do
  grep -Fq 'scripts/backend-python-format' "$ROOT/$caller" || fail "$caller bypasses the formatter primitive"
  if grep -Eq 'black==[0-9]+\.[0-9]+\.[0-9]+' "$ROOT/$caller"; then
    fail "$caller duplicates the Black version pin"
  fi
done

echo "backend Python formatter contract tests passed"
