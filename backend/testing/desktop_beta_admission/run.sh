#!/usr/bin/env bash
# Execute the loopback-only Firestore admission proof in an isolated emulator.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
firebase_tools_version="15.22.0"

if [[ -x "$repo_root/backend/.venv/bin/python" ]]; then
  python_command=("$repo_root/backend/.venv/bin/python")
elif command -v uv >/dev/null 2>&1; then
  python_version="$(tr -d '[:space:]' < "$repo_root/backend/.python-version")"
  python_command=(
    uv run --no-project --python "$python_version"
    --with "google-cloud-firestore==2.20.0" -- python
  )
else
  echo "Missing backend/.venv and uv. Run backend/scripts/sync-python-deps.sh first." >&2
  exit 1
fi

# Prefer the maintained local toolchains, while allowing CI to provide them on
# PATH. Firebase Tools needs a current Node runtime and Firestore needs Java 21.
node_prefix="$(brew --prefix node@22 2>/dev/null || true)"
if [[ -n "$node_prefix" && -x "$node_prefix/bin/node" ]]; then
  node_bin="$node_prefix/bin/node"
  export PATH="$node_prefix/bin:$PATH"
elif node_bin="$(command -v node 2>/dev/null)" && [[ -n "$node_bin" ]]; then
  :
else
  echo "Firestore emulator prerequisite missing: install Node 22 with brew install node@22." >&2
  exit 1
fi
node_major="$($node_bin -p 'process.versions.node.split(".")[0]')"
if [[ "$node_major" -lt 22 ]]; then
  echo "Firestore emulator prerequisite missing: Node 22+ is required (found $($node_bin --version))." >&2
  exit 1
fi

jdk_prefix="$(brew --prefix openjdk@21 2>/dev/null || true)"
if [[ -n "$jdk_prefix" && -x "$jdk_prefix/libexec/openjdk.jdk/Contents/Home/bin/java" ]]; then
  export JAVA_HOME="$jdk_prefix/libexec/openjdk.jdk/Contents/Home"
  export PATH="$JAVA_HOME/bin:$PATH"
fi
if ! command -v java >/dev/null 2>&1; then
  echo "Firestore emulator prerequisite missing: install Java 21 with brew install openjdk@21." >&2
  exit 1
fi
java_major="$(java -XshowSettings:properties -version 2>&1 | awk -F= '/^[[:space:]]*java\.version =/{gsub(/^[[:space:]]+/, "", $2); split($2, version, "."); print version[1]; exit}')"
if [[ ! "$java_major" =~ ^[0-9]+$ || "$java_major" -lt 21 ]]; then
  echo "Firestore emulator prerequisite missing: Java 21+ is required." >&2
  exit 1
fi

emulator_port="$($node_bin -e 'const net = require("net"); const server = net.createServer(); server.listen(0, "127.0.0.1", () => { console.log(server.address().port); server.close(); });')"
emulator_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-desktop-beta-admission.XXXXXX")"
emulator_config="$emulator_dir/firebase.json"
trap 'rm -rf "$emulator_dir"' EXIT
$node_bin -e 'require("fs").writeFileSync(process.argv[1], JSON.stringify({emulators: {firestore: {host: "127.0.0.1", port: Number(process.argv[2])}}}))' \
  "$emulator_config" "$emulator_port"

printf -v quoted_python_command ' %q' "${python_command[@]}"
printf -v quoted_test_path '%q' "$repo_root/backend/testing/desktop_beta_admission/firestore_contention_test.py"
printf -v quoted_python_path '%q' "$repo_root/backend"
runner_command="FIRESTORE_EMULATOR_HOST=127.0.0.1:${emulator_port} GOOGLE_CLOUD_PROJECT=demo-desktop-beta GCLOUD_PROJECT=demo-desktop-beta PYTHONPATH=${quoted_python_path}${quoted_python_command} ${quoted_test_path}"
firebase_command=(npx --prefix "$repo_root" --yes "firebase-tools@${firebase_tools_version}" emulators:exec --only firestore --project demo-desktop-beta --config "$emulator_config" "$runner_command")

# Firebase writes its debug logs to the current directory, so never launch it
# from the checkout. The emulator process and test also have a hard timeout.
cd "$emulator_dir"
if command -v gtimeout >/dev/null 2>&1; then
  gtimeout --preserve-status --kill-after=10s 180s "${firebase_command[@]}"
else
  "$node_bin" - "${firebase_command[@]}" <<'NODE'
const {spawn} = require("child_process");
const child = spawn(process.argv[2], process.argv.slice(3), {stdio: "inherit"});
const timer = setTimeout(() => {
  console.error("ERROR: desktop Beta admission emulator harness exceeded 180 seconds");
  child.kill("SIGTERM");
  setTimeout(() => child.kill("SIGKILL"), 10_000).unref();
}, 180_000);
child.on("exit", (code, signal) => {
  clearTimeout(timer);
  process.exitCode = code ?? (signal ? 1 : 0);
});
NODE
fi
