#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_DIR="$DESKTOP_DIR/agent"
PI_MONO_DIR="$DESKTOP_DIR/pi-mono-extension"
NODE_RESOURCE="$DESKTOP_DIR/Desktop/Sources/Resources/node"

NODE_VERSION="${OMI_AGENT_NODE_VERSION:-v22.14.0}"
NODE_DARWIN_ARM64_SHA256="e9404633bc02a5162c5c573b1e2490f5fb44648345d64a958b17e325729a5e42"
NODE_DARWIN_X64_SHA256="6698587713ab565a94a360e091df9f6d91c8fadda6d00f0cf6526e9b40bed250"

MODE="local"
SKIP_NPM=0

usage() {
  cat <<'USAGE'
Usage: scripts/prepare-agent-runtime.sh [--local-node|--universal-node] [--skip-npm]

Prepares the desktop Ask Omi agent runtime:
  - installs agent npm dependencies with npm ci
  - compiles agent/dist
  - stages Desktop/Sources/Resources/node for SwiftPM resource bundling
  - validates bridge, piMono, and extension files that the app launches at runtime

Modes:
  --local-node      Copy the developer's current `node` binary into resources.
  --universal-node  Download checksum-verified darwin arm64/x64 Node and lipo it.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --local-node)
      MODE="local"
      ;;
    --universal-node)
      MODE="universal"
      ;;
    --skip-npm)
      SKIP_NPM=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

log() {
  printf '[agent-runtime] %s\n' "$*"
}

require_file() {
  if [ ! -f "$1" ]; then
    echo "ERROR: missing required runtime file: $1" >&2
    exit 1
  fi
}

require_executable() {
  if [ ! -x "$1" ]; then
    echo "ERROR: missing required executable runtime file: $1" >&2
    exit 1
  fi
}

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

verify_sha256() {
  local file="$1"
  local expected="$2"
  local actual
  actual="$(sha256_file "$file")"
  if [ "$actual" != "$expected" ]; then
    echo "ERROR: checksum mismatch for $file" >&2
    echo "  expected: $expected" >&2
    echo "  actual:   $actual" >&2
    exit 1
  fi
}

install_agent_deps_and_build() {
  require_file "$AGENT_DIR/package-lock.json"
  require_file "$AGENT_DIR/package.json"

  if [ "$SKIP_NPM" = "1" ]; then
    log "Skipping npm install/build"
    return
  fi

  log "Installing agent dependencies with npm ci"
  (
    cd "$AGENT_DIR"
    npm ci --no-fund --no-audit
    npm run build --silent
  )
}

stage_local_node() {
  local node_bin
  node_bin="$(command -v node || true)"
  if [ -z "$node_bin" ]; then
    echo "ERROR: Node.js not found. Install Node.js 22+ or run release packaging with --universal-node." >&2
    exit 1
  fi

  local node_major
  node_major="$("$node_bin" -e 'console.log(process.versions.node.split(".")[0])')"
  if [ "$node_major" -lt 22 ]; then
    echo "ERROR: Node.js 22+ is required for the agent runtime; found $("$node_bin" --version) at $node_bin" >&2
    exit 1
  fi

  mkdir -p "$(dirname "$NODE_RESOURCE")"
  cp -f "$node_bin" "$NODE_RESOURCE"
  chmod +x "$NODE_RESOURCE"
  xattr -cr "$NODE_RESOURCE" 2>/dev/null || true

  # Homebrew's node is a stub dynamically linked to libnode.dylib via @rpath,
  # so the copied binary aborts at startup outside its install prefix. Fall back
  # to the self-contained official build when the staged copy can't run alone.
  local staged_version
  if ! staged_version="$("$NODE_RESOURCE" --version 2>/dev/null)"; then
    log "Local Node at $node_bin is not self-contained (dynamically linked, e.g. Homebrew); falling back to official Node $NODE_VERSION download"
    rm -f "$NODE_RESOURCE"
    stage_universal_node
    return
  fi
  log "Staged local Node $staged_version from $node_bin"
}

download_node_archive() {
  local arch="$1"
  local sha="$2"
  local out="$3"
  local url="https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-darwin-$arch.tar.gz"

  log "Downloading Node $NODE_VERSION darwin-$arch"
  curl -L --fail --show-error -o "$out" "$url"
  verify_sha256 "$out" "$sha"
}

stage_universal_node() {
  local temp_dir
  temp_dir="$(mktemp -d /tmp/omi-node-universal-XXXXXX)"
  trap "rm -rf '$temp_dir'" EXIT

  download_node_archive "arm64" "$NODE_DARWIN_ARM64_SHA256" "$temp_dir/arm64.tar.gz"
  tar -xzf "$temp_dir/arm64.tar.gz" -C "$temp_dir"
  local arm64_node="$temp_dir/node-$NODE_VERSION-darwin-arm64/bin/node"
  require_executable "$arm64_node"

  download_node_archive "x64" "$NODE_DARWIN_X64_SHA256" "$temp_dir/x64.tar.gz"
  tar -xzf "$temp_dir/x64.tar.gz" -C "$temp_dir"
  local x64_node="$temp_dir/node-$NODE_VERSION-darwin-x64/bin/node"
  require_executable "$x64_node"

  mkdir -p "$(dirname "$NODE_RESOURCE")"
  lipo -create "$arm64_node" "$x64_node" -output "$NODE_RESOURCE"
  chmod +x "$NODE_RESOURCE"
  xattr -cr "$NODE_RESOURCE" 2>/dev/null || true
  file "$NODE_RESOURCE" | grep -q "universal binary" || {
    echo "ERROR: staged Node is not universal: $(file "$NODE_RESOURCE")" >&2
    exit 1
  }
  log "Staged universal Node $NODE_VERSION at $NODE_RESOURCE"
}

validate_runtime_tree() {
  require_executable "$NODE_RESOURCE"
  require_file "$AGENT_DIR/dist/index.js"
  require_file "$AGENT_DIR/dist/patched-acp-entry.mjs"
  require_file "$AGENT_DIR/node_modules/@mariozechner/pi-coding-agent/dist/cli.js"
  require_file "$AGENT_DIR/node_modules/@zed-industries/claude-agent-acp/dist/acp-agent.js"
  require_file "$PI_MONO_DIR/index.ts"
  require_file "$PI_MONO_DIR/package.json"

  "$NODE_RESOURCE" --version >/dev/null
  log "Runtime validated: node=$("$NODE_RESOURCE" --version), agent dist and piMono files present"
}

install_agent_deps_and_build
case "$MODE" in
  local)
    stage_local_node
    ;;
  universal)
    stage_universal_node
    ;;
esac
validate_runtime_tree
