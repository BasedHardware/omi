#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_DIR="$DESKTOP_DIR/agent"
PI_MONO_DIR="$DESKTOP_DIR/pi-mono-extension"
NODE_RESOURCE="$DESKTOP_DIR/Desktop/Sources/Resources/node"
PACKAGED_RUNTIME_DIR="$DESKTOP_DIR/.harness/agent-runtime"
AGENT_PACKAGED_NODE_MODULES="$PACKAGED_RUNTIME_DIR/agent-node_modules"
PI_MONO_PACKAGED_NODE_MODULES="$PACKAGED_RUNTIME_DIR/pi-mono-extension-node_modules"

NODE_VERSION="${OMI_AGENT_NODE_VERSION:-v22.14.0}"
NODE_DARWIN_ARM64_SHA256="e9404633bc02a5162c5c573b1e2490f5fb44648345d64a958b17e325729a5e42"
NODE_DARWIN_X64_SHA256="6698587713ab565a94a360e091df9f6d91c8fadda6d00f0cf6526e9b40bed250"

MODE="universal"
SKIP_NPM=0

usage() {
  cat <<'USAGE'
Usage: scripts/prepare-agent-runtime.sh [--universal-node|--unsafe-local-node] [--skip-npm]

Prepares the desktop Ask Omi agent runtime:
  - installs agent npm dependencies with npm ci
  - compiles agent/dist
  - stages production-only node_modules for app packaging
  - stages Desktop/Sources/Resources/node for SwiftPM resource bundling
  - validates bridge, piMono, and extension files that the app launches at runtime

Modes:
  --universal-node  Download checksum-verified darwin arm64/x64 Node and lipo it.
  --unsafe-local-node
                    Copy the developer's current `node` binary into resources.
                    This is for debugging only; normal app bundles should use
                    the pinned universal runtime.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --universal-node)
      MODE="universal"
      ;;
    --unsafe-local-node)
      MODE="local"
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
  stage_production_node_modules "$AGENT_DIR" "$AGENT_PACKAGED_NODE_MODULES"
}

install_pi_mono_deps() {
  require_file "$PI_MONO_DIR/package-lock.json"
  require_file "$PI_MONO_DIR/package.json"

  if [ "$SKIP_NPM" = "1" ]; then
    return
  fi

  log "Installing pi-mono-extension production dependencies for packaging"
  (
    cd "$PI_MONO_DIR"
    npm ci --omit=dev --no-fund --no-audit
  )
  stage_production_node_modules "$PI_MONO_DIR" "$PI_MONO_PACKAGED_NODE_MODULES"
  dedupe_pi_mono_packaged_node_modules
}

stage_production_node_modules() {
  local package_dir="$1"
  local output_dir="$2"
  local temp_dir

  require_file "$package_dir/package-lock.json"
  require_file "$package_dir/package.json"

  mkdir -p "$PACKAGED_RUNTIME_DIR"
  temp_dir="$(mktemp -d "$PACKAGED_RUNTIME_DIR/$(basename "$package_dir").XXXXXX")"
  cp -f "$package_dir/package.json" "$package_dir/package-lock.json" "$temp_dir/"

  log "Staging $(basename "$package_dir") production dependencies for packaging"
  (
    cd "$temp_dir"
    npm ci --omit=dev --no-fund --no-audit
  )

  prune_non_macos_node_packages "$temp_dir"
  prune_packaged_node_modules "$temp_dir"
  rm -rf "$output_dir"
  mv "$temp_dir/node_modules" "$output_dir"
  rm -rf "$temp_dir"
}

prune_non_macos_node_packages() {
  local package_dir="$1"

  node - "$package_dir" <<'NODE'
const fs = require("node:fs");
const path = require("node:path");

const packageDir = process.argv[2];
const lockPath = path.join(packageDir, "package-lock.json");
const nodeModulesPath = path.join(packageDir, "node_modules");

if (!fs.existsSync(lockPath) || !fs.existsSync(nodeModulesPath)) {
  process.exit(0);
}

const lock = JSON.parse(fs.readFileSync(lockPath, "utf8"));
const packages = lock.packages || {};
let removedCount = 0;
let removedBytes = 0;

function directorySizeBytes(targetPath) {
  let total = 0;
  for (const entry of fs.readdirSync(targetPath, { withFileTypes: true })) {
    const entryPath = path.join(targetPath, entry.name);
    if (entry.isDirectory()) {
      total += directorySizeBytes(entryPath);
    } else if (entry.isFile()) {
      total += fs.statSync(entryPath).size;
    }
  }
  return total;
}

function excludesDarwin(packageMeta) {
  return Array.isArray(packageMeta.os) && !packageMeta.os.includes("darwin");
}

for (const [lockPackagePath, packageMeta] of Object.entries(packages)) {
  if (!lockPackagePath.startsWith("node_modules/") || !excludesDarwin(packageMeta)) {
    continue;
  }

  const installedPath = path.join(packageDir, lockPackagePath);
  if (!fs.existsSync(installedPath)) {
    continue;
  }

  removedBytes += directorySizeBytes(installedPath);
  fs.rmSync(installedPath, { recursive: true, force: true });
  removedCount += 1;
}

if (removedCount > 0) {
  const removedMiB = (removedBytes / 1024 / 1024).toFixed(1);
  console.log(`[agent-runtime] Pruned ${removedCount} non-macOS package(s) from ${path.basename(packageDir)} (${removedMiB} MiB)`);
}
NODE
}

prune_packaged_node_modules() {
  local package_dir="$1"

  node - "$package_dir" <<'NODE'
const fs = require("node:fs");
const path = require("node:path");

const packageDir = process.argv[2];
const nodeModulesPath = path.join(packageDir, "node_modules");

if (!fs.existsSync(nodeModulesPath)) {
  process.exit(0);
}

let removedCount = 0;
let removedBytes = 0;

function removePath(targetPath) {
  if (!fs.existsSync(targetPath)) {
    return;
  }
  removedBytes += pathSizeBytes(targetPath);
  fs.rmSync(targetPath, { recursive: true, force: true });
  removedCount += 1;
}

function pathSizeBytes(targetPath) {
  const stat = fs.lstatSync(targetPath);
  if (stat.isSymbolicLink()) {
    return 0;
  }
  if (stat.isFile()) {
    return stat.size;
  }
  if (!stat.isDirectory()) {
    return 0;
  }

  let total = 0;
  for (const entry of fs.readdirSync(targetPath, { withFileTypes: true })) {
    total += pathSizeBytes(path.join(targetPath, entry.name));
  }
  return total;
}

function walk(targetPath, visit) {
  if (!fs.existsSync(targetPath)) {
    return;
  }
  for (const entry of fs.readdirSync(targetPath, { withFileTypes: true })) {
    const entryPath = path.join(targetPath, entry.name);
    if (visit(entryPath, entry) === false) {
      continue;
    }
    if (entry.isDirectory() && !entry.isSymbolicLink()) {
      walk(entryPath, visit);
    }
  }
}

walk(nodeModulesPath, (entryPath, entry) => {
  if (entry.isFile() && (entry.name.endsWith(".map") || entry.name.endsWith(".tsbuildinfo"))) {
    removePath(entryPath);
    return false;
  }
});

removePath(path.join(nodeModulesPath, "@mariozechner", "pi-coding-agent", "docs"));

for (const koffiDir of [
  path.join(nodeModulesPath, "koffi", "build", "koffi"),
]) {
  if (!fs.existsSync(koffiDir)) {
    continue;
  }
  for (const entry of fs.readdirSync(koffiDir, { withFileTypes: true })) {
    if (!entry.isDirectory() || ["darwin_arm64", "darwin_x64"].includes(entry.name)) {
      continue;
    }
    removePath(path.join(koffiDir, entry.name));
  }
}

const ripgrepDir = path.join(
  nodeModulesPath,
  "@anthropic-ai",
  "claude-agent-sdk",
  "vendor",
  "ripgrep"
);
if (fs.existsSync(ripgrepDir)) {
  for (const entry of fs.readdirSync(ripgrepDir, { withFileTypes: true })) {
    if (!entry.isDirectory() || ["arm64-darwin", "x64-darwin"].includes(entry.name)) {
      continue;
    }
    removePath(path.join(ripgrepDir, entry.name));
  }
}

if (removedCount > 0) {
  const removedMiB = (removedBytes / 1024 / 1024).toFixed(1);
  console.log(`[agent-runtime] Pruned ${removedCount} packaged-only file(s)/folder(s) from ${path.basename(packageDir)} (${removedMiB} MiB)`);
}
NODE
}

dedupe_pi_mono_packaged_node_modules() {
  node - "$AGENT_PACKAGED_NODE_MODULES" "$PI_MONO_PACKAGED_NODE_MODULES" <<'NODE'
const fs = require("node:fs");
const path = require("node:path");

const agentNodeModules = process.argv[2];
const piNodeModules = process.argv[3];

if (!fs.existsSync(agentNodeModules) || !fs.existsSync(piNodeModules)) {
  process.exit(0);
}

let linkedCount = 0;
let linkedBytes = 0;

function directorySizeBytes(targetPath) {
  const stat = fs.lstatSync(targetPath);
  if (stat.isSymbolicLink()) {
    return 0;
  }
  if (stat.isFile()) {
    return stat.size;
  }
  if (!stat.isDirectory()) {
    return 0;
  }

  let total = 0;
  for (const entry of fs.readdirSync(targetPath, { withFileTypes: true })) {
    total += directorySizeBytes(path.join(targetPath, entry.name));
  }
  return total;
}

function packageJson(packagePath) {
  const jsonPath = path.join(packagePath, "package.json");
  if (!fs.existsSync(jsonPath)) {
    return undefined;
  }
  return JSON.parse(fs.readFileSync(jsonPath, "utf8"));
}

function samePackageVersion(piPackagePath, agentPackagePath) {
  const piPackage = packageJson(piPackagePath);
  const agentPackage = packageJson(agentPackagePath);
  return Boolean(
    piPackage &&
      agentPackage &&
      piPackage.name === agentPackage.name &&
      piPackage.version === agentPackage.version
  );
}

function finalBundleSymlinkTarget(packageName) {
  if (packageName.startsWith("@")) {
    return `../../../agent/node_modules/${packageName}`;
  }
  return `../../agent/node_modules/${packageName}`;
}

function linkPackage(piPackagePath, packageName) {
  linkedBytes += directorySizeBytes(piPackagePath);
  fs.rmSync(piPackagePath, { recursive: true, force: true });
  fs.symlinkSync(finalBundleSymlinkTarget(packageName), piPackagePath, "dir");
  linkedCount += 1;
}

for (const entry of fs.readdirSync(piNodeModules, { withFileTypes: true })) {
  if (entry.name === ".bin" || entry.name === ".package-lock.json") {
    continue;
  }

  const piEntryPath = path.join(piNodeModules, entry.name);
  const agentEntryPath = path.join(agentNodeModules, entry.name);

  if (entry.isDirectory() && entry.name.startsWith("@")) {
    if (!fs.existsSync(agentEntryPath)) {
      continue;
    }
    for (const scopedEntry of fs.readdirSync(piEntryPath, { withFileTypes: true })) {
      if (!scopedEntry.isDirectory()) {
        continue;
      }
      const piPackagePath = path.join(piEntryPath, scopedEntry.name);
      const agentPackagePath = path.join(agentEntryPath, scopedEntry.name);
      const packageName = `${entry.name}/${scopedEntry.name}`;
      if (samePackageVersion(piPackagePath, agentPackagePath)) {
        linkPackage(piPackagePath, packageName);
      }
    }
    continue;
  }

  if (!entry.isDirectory() || !samePackageVersion(piEntryPath, agentEntryPath)) {
    continue;
  }
  linkPackage(piEntryPath, entry.name);
}

if (linkedCount > 0) {
  const linkedMiB = (linkedBytes / 1024 / 1024).toFixed(1);
  console.log(`[agent-runtime] Deduped ${linkedCount} pi-mono package(s) via symlink (${linkedMiB} MiB)`);
}
NODE
}

stage_unsafe_local_node() {
  local node_bin
  node_bin="$(command -v node || true)"
  if [ -z "$node_bin" ]; then
    echo "ERROR: Node.js not found. Install Node.js 22+ or use --universal-node." >&2
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
    log "Unsafe local Node at $node_bin is not self-contained (dynamically linked, e.g. Homebrew); falling back to official Node $NODE_VERSION download"
    rm -f "$NODE_RESOURCE"
    stage_universal_node
    return
  fi
  log "Staged unsafe local Node $staged_version from $node_bin"
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
  require_file "$AGENT_DIR/src/runtime/control-tool-manifest.js"
  require_file "$AGENT_DIR/src/runtime/control-tool-manifest.ts"
  require_file "$AGENT_DIR/src/runtime/node-tools.ts"
  require_file "$AGENT_DIR/src/runtime/omi-tool-manifest.ts"
  require_file "$AGENT_DIR/node_modules/@mariozechner/pi-coding-agent/dist/cli.js"
  require_file "$AGENT_PACKAGED_NODE_MODULES/@mariozechner/pi-coding-agent/dist/cli.js"
  require_file "$AGENT_DIR/node_modules/@zed-industries/claude-agent-acp/dist/acp-agent.js"
  require_file "$AGENT_PACKAGED_NODE_MODULES/@zed-industries/claude-agent-acp/dist/acp-agent.js"
  require_file "$PI_MONO_DIR/index.ts"
  require_file "$PI_MONO_DIR/package.json"
  require_file "$PI_MONO_PACKAGED_NODE_MODULES/@mariozechner/pi-coding-agent/dist/cli.js"

  "$NODE_RESOURCE" --version >/dev/null
  log "Runtime validated: node=$("$NODE_RESOURCE" --version), agent dist and piMono files present"
}

install_agent_deps_and_build
install_pi_mono_deps
case "$MODE" in
  local)
    stage_unsafe_local_node
    ;;
  universal)
    stage_universal_node
    ;;
esac
validate_runtime_tree
