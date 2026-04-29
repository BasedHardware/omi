#!/usr/bin/env bash
#
# Build a self-contained Pi coding-agent binary for the current platform
# using `bun build --compile`, then copy the runtime assets Pi expects to
# find alongside its executable.
#
# Output layout (all under sidecar/pi-agent/dist/):
#   nooto-pi-agent-<triple>   ← compiled binary (declared in tauri.conf.json externalBin)
#   package.json              ← Pi reads this for its version string
#   theme/                    ← built-in colour themes (dark.json, light.json, …)
#   assets/                   ← interactive-mode images
#   export-html/              ← HTML export template
#   photon_rs_bg.wasm         ← image-processing WASM module
#   extensions/               ← nooto-backend + nooto-permissions TS extensions
#                                (resolved at runtime by Rust via resource_dir)
#
# Supported targets:
#   darwin-arm64    [MVP — implemented]
#   darwin-x86_64   [TODO: add when CI supports an x86_64 macOS runner]
#   linux-x64       [TODO: add for Linux desktop builds]
#   windows-x64     [TODO: add for Windows desktop builds]
#
# Usage:
#   cd src-tauri/sidecar/pi-agent
#   bash scripts/build-binary.sh
#
# Requirements: bun >= 1.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIDECAR_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$SIDECAR_DIR/dist"
PI_PKG_DIR="$SIDECAR_DIR/node_modules/@mariozechner/pi-coding-agent"
ENTRY="$PI_PKG_DIR/dist/bun/cli.js"

if [ ! -f "$ENTRY" ]; then
  echo "ERROR: Entry point not found: $ENTRY" >&2
  echo "       Run 'pnpm install' inside src-tauri/sidecar/pi-agent/ first." >&2
  exit 1
fi

if ! command -v bun &>/dev/null; then
  echo "ERROR: bun is not installed or not on PATH." >&2
  exit 1
fi

mkdir -p "$DIST_DIR"

# ---------------------------------------------------------------------------
# Detect host platform and set the Tauri-friendly target triple
# ---------------------------------------------------------------------------
HOST_OS="$(uname -s)"
HOST_ARCH="$(uname -m)"

case "${HOST_OS}-${HOST_ARCH}" in
  Darwin-arm64)
    TAURI_TRIPLE="aarch64-apple-darwin"
    BUN_TARGET="bun-darwin-arm64"
    ;;
  Darwin-x86_64)
    TAURI_TRIPLE="x86_64-apple-darwin"
    BUN_TARGET="bun-darwin-x64"
    # TODO: This target is not yet tested in CI.
    echo "WARNING: darwin-x86_64 target is not yet validated in CI." >&2
    ;;
  Linux-x86_64)
    TAURI_TRIPLE="x86_64-unknown-linux-gnu"
    BUN_TARGET="bun-linux-x64"
    # TODO: This target is not yet tested in CI.
    echo "WARNING: linux-x64 target is not yet validated in CI." >&2
    ;;
  *)
    echo "ERROR: Unsupported host platform: ${HOST_OS}-${HOST_ARCH}" >&2
    echo "       Supported: darwin-arm64 (MVP), darwin-x86_64, linux-x64" >&2
    exit 1
    ;;
esac

OUTFILE="$DIST_DIR/nooto-pi-agent-$TAURI_TRIPLE"

echo "==> Building Pi binary"
echo "    entry:  $ENTRY"
echo "    target: $BUN_TARGET"
echo "    output: $OUTFILE"

bun build \
  --compile \
  --target="$BUN_TARGET" \
  --minify \
  "$ENTRY" \
  --outfile "$OUTFILE"

chmod +x "$OUTFILE"

# ---------------------------------------------------------------------------
# Copy runtime assets Pi expects to find next to its executable.
#
# Pi's config.js detects a Bun binary via `isBunBinary` and then resolves all
# asset paths as `dirname(process.execPath)/<asset>`.  Without these files the
# binary exits with ENOENT on startup.
# ---------------------------------------------------------------------------

echo "==> Copying Pi runtime assets"

# package.json — Pi reads this for its version string and piConfig.
cp "$PI_PKG_DIR/package.json" "$DIST_DIR/package.json"
echo "    package.json"

# theme/ — built-in colour themes (dark.json, light.json, theme-schema.json).
mkdir -p "$DIST_DIR/theme"
cp "$PI_PKG_DIR/dist/modes/interactive/theme/"*.json "$DIST_DIR/theme/"
echo "    theme/"

# assets/ — interactive-mode PNG images.
mkdir -p "$DIST_DIR/assets"
cp "$PI_PKG_DIR/dist/modes/interactive/assets/"*.png "$DIST_DIR/assets/"
echo "    assets/"

# export-html/ — HTML export template + optional vendor JS.
mkdir -p "$DIST_DIR/export-html"
cp "$PI_PKG_DIR/dist/core/export-html/template.html" "$DIST_DIR/export-html/"
cp "$PI_PKG_DIR/dist/core/export-html/template.css"  "$DIST_DIR/export-html/" 2>/dev/null || true
cp "$PI_PKG_DIR/dist/core/export-html/template.js"   "$DIST_DIR/export-html/" 2>/dev/null || true
if ls "$PI_PKG_DIR/dist/core/export-html/vendor/"*.js &>/dev/null 2>&1; then
  mkdir -p "$DIST_DIR/export-html/vendor"
  cp "$PI_PKG_DIR/dist/core/export-html/vendor/"*.js "$DIST_DIR/export-html/vendor/"
fi
echo "    export-html/"

# photon_rs_bg.wasm — image-processing WASM module bundled with pi.
PHOTON_WASM="$(find "$SIDECAR_DIR/node_modules" -name "photon_rs_bg.wasm" 2>/dev/null | head -1)"
if [ -n "$PHOTON_WASM" ]; then
  cp "$PHOTON_WASM" "$DIST_DIR/photon_rs_bg.wasm"
  echo "    photon_rs_bg.wasm"
else
  echo "    photon_rs_bg.wasm (not found — skipping)"
fi

# ---------------------------------------------------------------------------
# Copy extensions next to the binary for development use.
# In a production .app bundle, extensions are declared in tauri.conf.json
# `bundle.resources` and Tauri copies them into Contents/Resources/; the Rust
# code resolves them via app.path().resource_dir().
# ---------------------------------------------------------------------------

echo "==> Copying extensions"
DIST_EXT_DIR="$DIST_DIR/extensions"
mkdir -p "$DIST_EXT_DIR"

for EXT_NAME in nooto-backend nooto-permissions; do
  EXT_SRC="$SIDECAR_DIR/extensions/$EXT_NAME"
  if [ -d "$EXT_SRC" ]; then
    cp -r "$EXT_SRC" "$DIST_EXT_DIR/"
    echo "    $EXT_NAME"
  else
    echo "    $EXT_NAME (absent — skipping)"
  fi
done

echo ""
echo "==> Done"
echo "    Binary : $OUTFILE"
echo "    Size   : $(du -sh "$OUTFILE" | cut -f1)"
