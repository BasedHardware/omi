#!/usr/bin/env bash
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="$(cd "$MACOS_DIR/.." && pwd)"
OUTPUT_DIR="$MACOS_DIR/Desktop/Generated/OmiDesktopCoreFFI"
SWIFT_OUTPUT="$MACOS_DIR/Desktop/Sources/Generated/OmiDesktopCore.swift"
PROFILE="${OMI_DESKTOP_CORE_PROFILE:-debug}"
CARGO_PROFILE_ARGS=()
if [[ "$PROFILE" == "release" ]]; then
  CARGO_PROFILE_ARGS+=(--release)
fi

mkdir -p "$OUTPUT_DIR"
cd "$DESKTOP_DIR"
cargo build -p omi-desktop-core --locked "${CARGO_PROFILE_ARGS[@]+${CARGO_PROFILE_ARGS[@]}}"
cargo run -p omi-desktop-core --bin uniffi-bindgen --features uniffi-bindgen --locked "${CARGO_PROFILE_ARGS[@]+${CARGO_PROFILE_ARGS[@]}}" -- generate \
  --library "target/$PROFILE/libomi_desktop_core.dylib" \
  --language swift \
  --out-dir "$OUTPUT_DIR"
cp "$OUTPUT_DIR/omi_desktop_core.swift" "$SWIFT_OUTPUT"
cp "$OUTPUT_DIR/omi_desktop_coreFFI.modulemap" "$OUTPUT_DIR/module.modulemap"
cp "target/$PROFILE/libomi_desktop_core.dylib" "$OUTPUT_DIR/libomi_desktop_core.dylib"
