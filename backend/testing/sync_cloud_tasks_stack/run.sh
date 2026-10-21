#!/usr/bin/env bash
# Run through Firebase so Firestore is isolated and torn down automatically.
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

emulator_ports="$(node -e 'const net = require("net"); const servers = [net.createServer(), net.createServer()]; let ready = 0; for (const server of servers) server.listen(0, "127.0.0.1", () => { if (++ready === servers.length) { console.log(servers.map(item => item.address().port).join(" ")); for (const item of servers) item.close(); } });')"
read -r emulator_port emulator_websocket_port <<< "$emulator_ports"
emulator_config="$(mktemp "${TMPDIR:-/tmp}/omi-sync-cloud-tasks-firebase.XXXXXX")"
trap 'rm -f "$emulator_config"' EXIT
node -e 'require("fs").writeFileSync(process.argv[1], JSON.stringify({emulators: {firestore: {host: "127.0.0.1", port: Number(process.argv[2]), websocketPort: Number(process.argv[3])}}}))' \
  "$emulator_config" "$emulator_port" "$emulator_websocket_port"

runner_command="PYTHONPATH=backend backend/.venv/bin/python -m testing.sync_cloud_tasks_stack.run"
for argument in "$@"; do
  printf -v escaped_argument ' %q' "$argument"
  runner_command+="$escaped_argument"
done

npx --no-install firebase emulators:exec --only firestore --project demo-omi-sync-cloud-tasks-stack --config "$emulator_config" \
  "$runner_command"
