#!/usr/bin/env bash
# Run through Firebase so Firestore is isolated and torn down automatically.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$repo_root"

if [[ ! -x backend/.venv/bin/python ]]; then
  echo "Missing backend/.venv. Run backend/scripts/sync-python-deps.sh first." >&2
  exit 1
fi

# Firebase's Firestore emulator is a JVM process.  Prefer an already-configured
# Java, then make Homebrew's keg-only OpenJDK usable without asking every
# developer to modify a shell profile. Firebase CLI currently requires 21+.
if ! java -version >/dev/null 2>&1; then
  jdk_prefix="$(brew --prefix openjdk@21 2>/dev/null || true)"
  if [[ -n "$jdk_prefix" && -x "$jdk_prefix/libexec/openjdk.jdk/Contents/Home/bin/java" ]]; then
    export JAVA_HOME="$jdk_prefix/libexec/openjdk.jdk/Contents/Home"
    export PATH="$JAVA_HOME/bin:$PATH"
  fi
fi
if ! java -version >/dev/null 2>&1; then
  echo "Firebase's Firestore emulator needs Java 21+. Install it with: brew install openjdk@21" >&2
  exit 1
fi

# The repository firebase.json intentionally has stable shared ports. Generate
# a minimal config for this one local run instead, so it cannot collide with a
# developer emulator or any other test worktree.
emulator_port="$(node -e 'const net = require("net"); const server = net.createServer(); server.listen(0, "127.0.0.1", () => { console.log(server.address().port); server.close(); });')"
emulator_config="$(mktemp "${TMPDIR:-/tmp}/omi-listen-pusher-firebase.XXXXXX")"
trap 'rm -f "$emulator_config"' EXIT
node -e 'require("fs").writeFileSync(process.argv[1], JSON.stringify({emulators: {firestore: {host: "127.0.0.1", port: Number(process.argv[2])}}}))' \
  "$emulator_config" "$emulator_port"

runner_command="PYTHONPATH=backend backend/.venv/bin/python -m testing.listen_pusher_stack.run && PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/unit/test_stale_processing_emulator_concurrency.py -v"
for argument in "$@"; do
  printf -v escaped_argument ' %q' "$argument"
  runner_command+="$escaped_argument"
done

npx --no-install firebase emulators:exec --only firestore --project demo-omi-listen-stack --config "$emulator_config" \
  "$runner_command"
