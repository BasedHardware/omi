#!/usr/bin/env bash
# Run the Phase 0A replay harness through Firebase so Firestore is isolated
# and torn down automatically.
#
# FEASIBILITY-ONLY: this is an experiment, not a merge-blocking gauntlet.
# The existing sync_cloud_tasks_stack gauntlet remains the blocking coverage.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$repo_root"

if [[ ! -x backend/.venv/bin/python ]]; then
  echo "Missing backend/.venv. Run backend/scripts/sync-python-deps.sh first." >&2
  exit 1
fi

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

if ! command -v redis-server >/dev/null 2>&1; then
  echo "redis-server is required. Install Redis and retry." >&2
  exit 1
fi

emulator_port="$(node -e 'const net = require("net"); const server = net.createServer(); server.listen(0, "127.0.0.1", () => { console.log(server.address().port); server.close(); });')"
emulator_config="$(mktemp "${TMPDIR:-/tmp}/omi-replay-harness-firebase.XXXXXX")"
trap 'rm -f "$emulator_config"' EXIT
node -e 'require("fs").writeFileSync(process.argv[1], JSON.stringify({emulators: {firestore: {host: "127.0.0.1", port: Number(process.argv[2])}}}))' \
  "$emulator_config" "$emulator_port"

if [[ -z "${OMI_REPLAY_STATE_ROOT:-}" ]]; then
  state_root="$(mktemp -d "${TMPDIR:-/tmp}/omi-replay-harness.XXXXXX")"
else
  state_root="$OMI_REPLAY_STATE_ROOT"
fi
export OMI_REPLAY_STATE_ROOT="$state_root"

runner_command="PYTHONPATH=backend backend/.venv/bin/python -m testing.replay_harness_phase0a.runner"

echo "Phase 0A Replay Harness — feasibility experiment"
echo "  state root: $state_root"
echo "  Firestore emulator: 127.0.0.1:$emulator_port"

npx --no-install firebase emulators:exec --only firestore --project demo-omi-replay-harness --config "$emulator_config" \
  "$runner_command"
