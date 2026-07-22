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

emulator_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-desktop-beta-admission.XXXXXX")"
emulator_config="$emulator_dir/firebase.json"
config_writer="$repo_root/backend/testing/desktop_beta_admission/emulator_config.mjs"
supervisor="$repo_root/backend/testing/desktop_beta_admission/supervise.mjs"
trap 'rm -rf "$emulator_dir"' EXIT
read -r emulator_port websocket_port < <("$node_bin" "$config_writer" "$emulator_config")

printf -v quoted_python_command ' %q' "${python_command[@]}"
printf -v quoted_test_path '%q' "$repo_root/backend/testing/desktop_beta_admission/firestore_contention_test.py"
printf -v quoted_python_path '%q' "$repo_root/backend"
runner_command="FIRESTORE_EMULATOR_HOST=127.0.0.1:${emulator_port} GOOGLE_CLOUD_PROJECT=demo-desktop-beta GCLOUD_PROJECT=demo-desktop-beta PYTHONPATH=${quoted_python_path}${quoted_python_command} ${quoted_test_path}"
firebase_command=(npx --prefix "$repo_root" --yes "firebase-tools@${firebase_tools_version}" emulators:exec --only firestore --project demo-desktop-beta --config "$emulator_config" "$runner_command")

# Firebase writes its debug logs to the current directory, so never launch it
# from the checkout. The supervisor owns and drains the Firebase process group,
# including Firestore's JVM, before removing this isolated directory.
cd "$emulator_dir"
exec "$node_bin" "$supervisor" --timeout-seconds 180 --cleanup-path "$emulator_dir" -- "${firebase_command[@]}"
