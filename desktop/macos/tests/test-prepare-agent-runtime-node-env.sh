#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PREPARE_SCRIPT="$MACOS_DIR/scripts/prepare-agent-runtime.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# Regression for the agent build failing with hundreds of spurious tsc errors
# ("Cannot find module 'fs'", "Cannot find name 'process'") when a parent
# process (observed cause: Terminal.app inheriting NODE_ENV=production from
# an app that launched it) has NODE_ENV=production set: npm ci then silently
# omits devDependencies, so typescript/@types/node never install in the real
# agent/. Scoped to install_agent_deps_and_build's body so an unrelated npm
# ci elsewhere in the script (there are dev-omitting ones by design) can't be
# picked up by accident.
npm_ci_line="$(sed -n '/^install_agent_deps_and_build()/,/^}/p' "$PREPARE_SCRIPT" | grep -m1 -E '^[[:space:]]*npm ci ')"
[ -n "$npm_ci_line" ] || fail "could not find the npm ci invocation in install_agent_deps_and_build ($PREPARE_SCRIPT)"

# Exercise it against a throwaway fixture package instead of the real agent/
# lockfile so this test is hermetic (no registry network) regardless of npm
# cache state: one dependency, one devDependency, both local `file:` refs.
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/omi-prepare-agent-runtime-node-env-test.XXXXXX")"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

mkdir -p "$tmpdir/dep-pkg" "$tmpdir/devdep-pkg"
cat > "$tmpdir/dep-pkg/package.json" <<'EOF'
{"name":"dep-pkg","version":"1.0.0"}
EOF
cat > "$tmpdir/devdep-pkg/package.json" <<'EOF'
{"name":"devdep-pkg","version":"1.0.0"}
EOF
cat > "$tmpdir/package.json" <<'EOF'
{
  "name": "prepare-agent-runtime-node-env-fixture",
  "version": "1.0.0",
  "dependencies": { "dep-pkg": "file:./dep-pkg" },
  "devDependencies": { "devdep-pkg": "file:./devdep-pkg" }
}
EOF

(
  cd "$tmpdir"
  npm install --package-lock-only --offline --no-fund --no-audit >/dev/null
  # --offline: the extracted line already forces devDependencies via
  # --include=dev; --offline just guarantees this test can never fall back to
  # a real registry fetch, keeping it hermetic even if npm's local resolution
  # for the fixture's file: deps ever needed a cache lookup.
  NODE_ENV=production eval "$npm_ci_line --offline"
)

[ -d "$tmpdir/node_modules/dep-pkg" ] || fail "fixture setup is broken: the (non-dev) dependency did not install"
[ -d "$tmpdir/node_modules/devdep-pkg" ] || fail "devDependency was not installed under NODE_ENV=production (regressed: npm ci is omitting devDependencies)"

echo "prepare-agent-runtime node-env tests passed"
