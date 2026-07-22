#!/usr/bin/env bash

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-make-setup.XXXXXX")"
trap 'rm -rf "$TMPDIR"' EXIT

mkdir -p "$TMPDIR/repo/scripts/dev-harness" "$TMPDIR/repo/backend/scripts"
git init --initial-branch=main "$TMPDIR/repo" >/dev/null
cp "$ROOT/Makefile" "$TMPDIR/repo/Makefile"

cat >"$TMPDIR/repo/scripts/dev-harness/_resolve_python.sh" <<'EOF'
dev_harness_python() {
  printf '%s\n' python3
}
EOF

for script in setup-refresh-main.sh install-git-hooks.sh; do
  cat >"$TMPDIR/repo/scripts/$script" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$(basename "$0")" >> setup-order.txt
EOF
  chmod +x "$TMPDIR/repo/scripts/$script"
done

cat >"$TMPDIR/repo/backend/scripts/sync-python-deps.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "backend-sync" >> setup-order.txt
EOF
chmod +x "$TMPDIR/repo/backend/scripts/sync-python-deps.sh"

(
  cd "$TMPDIR/repo"
  make setup >/dev/null
)

expected=$'setup-refresh-main.sh\ninstall-git-hooks.sh\nbackend-sync'
actual="$(cat "$TMPDIR/repo/setup-order.txt")"
if [ "$actual" != "$expected" ]; then
  echo "FAIL: make setup did not provision baseline pre-push prerequisites in order." >&2
  printf 'Expected:\n%s\nActual:\n%s\n' "$expected" "$actual" >&2
  exit 1
fi

echo "make setup baseline prerequisites test passed."

# The baseline target is intentionally safe to rerun: an agent should not have
# to delete a healthy venv just to repeat setup after a branch change.
mkdir -p "$TMPDIR/sync/backend/scripts" "$TMPDIR/sync/bin"
cp "$ROOT/backend/scripts/sync-python-deps.sh" "$TMPDIR/sync/backend/scripts/sync-python-deps.sh"
printf '3.11\n' >"$TMPDIR/sync/backend/.python-version"
# The sync script selects a different checked-in lock by host platform.
# Keep this fixture runnable in macOS, Linux, Windows, and Intel-macOS CI.
touch \
  "$TMPDIR/sync/backend/pylock.toml" \
  "$TMPDIR/sync/backend/pylock.macos.toml" \
  "$TMPDIR/sync/backend/pylock.macos-x86_64.toml" \
  "$TMPDIR/sync/backend/pylock.windows.toml"
cat >"$TMPDIR/sync/bin/uv" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = "python" ]; then
  exit 0
fi
if [ "$1" = "venv" ]; then
  target="${!#}"
  if [ -e "$target" ] && [[ " $* " != *" --allow-existing "* ]]; then
    echo "refusing to replace existing venv" >&2
    exit 42
  fi
  mkdir -p "$target/bin"
  exit 0
fi
if [ "$1" = "pip" ] && [ "$2" = "sync" ]; then
  exit 0
fi
echo "unexpected uv invocation: $*" >&2
exit 1
EOF
chmod +x "$TMPDIR/sync/bin/uv"
(
  cd "$TMPDIR/sync/backend"
  PATH="$TMPDIR/sync/bin:$PATH" bash scripts/sync-python-deps.sh >/dev/null
  PATH="$TMPDIR/sync/bin:$PATH" bash scripts/sync-python-deps.sh >/dev/null
)

echo "backend dependency sync rerun test passed."
