#!/usr/bin/env bash
# Put the image's prebuilt environments where the harness looks for them, and leave the working tree
# exactly as we found it.
#
# Both are paths CI really has: it runs `uv venv .venv` in backend/ and `npm ci` at the repo root. Here
# the repo is a bind mount, so the image carries the two environments and links them in for the run —
# `run.sh` checks `backend/.venv/bin/python`, and it launches the emulator through `npx --no-install
# firebase`, which resolves only from a node_modules in the cwd tree. Both are gitignored, but a symlink
# pointing at a container path would be dead on the host, so they go away on the way out.
set -euo pipefail

link() {
    local target=$1 path=$2
    if [[ -e "$path" && ! -L "$path" ]]; then
        echo "$path exists and is not a symlink; refusing to touch it." >&2
        exit 1
    fi
    ln -sfn "$target" "$path"
    LINKS+=("$path")
}

LINKS=()
cleanup() { for path in "${LINKS[@]:-}"; do [[ -L "$path" ]] && rm -f "$path"; done; }
trap cleanup EXIT

link /opt/harness-venv /repo/backend/.venv
link /opt/harness-node/node_modules /repo/node_modules

# Java needs a writable home for the emulator jar it caches on first use, and npm for its own cache.
# Keep both inside the image rather than in the bind mount.
export HOME=/opt/harness-home
mkdir -p "$HOME"

exec "$@"
