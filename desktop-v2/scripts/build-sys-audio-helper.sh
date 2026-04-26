#!/usr/bin/env bash
# Build and sign the sys-audio-capture Swift helper.
#
# Output: swift-helpers/bin/sys-audio-capture
#
# Signed with the same Apple Development identity + entitlements as the
# main Rust binary so it inherits the audio-capture TCC grant.

set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$here/.." && pwd)"

src="$root/swift-helpers/sys-audio-capture/main.swift"
out_dir="$root/swift-helpers/bin"
out_bin="$out_dir/sys-audio-capture"
entitlements="$root/src-tauri/dev.entitlements"

mkdir -p "$out_dir"

# Skip rebuild if output is newer than source — speeds up tauri dev loop.
if [ -x "$out_bin" ] && [ "$out_bin" -nt "$src" ]; then
    exit 0
fi

echo "building $out_bin"
swiftc -O \
    -target arm64-apple-macos14.4 \
    -framework AVFoundation \
    -framework CoreAudio \
    -framework CoreMedia \
    -framework ScreenCaptureKit \
    -o "$out_bin" \
    "$src"

identity="${OMI_SIGN_IDENTITY:-}"
if [ -z "$identity" ]; then
    identity="$(security find-identity -v -p codesigning 2>/dev/null \
        | grep 'Apple Development' | head -1 \
        | sed 's/.*"\(.*\)"/\1/')"
fi
if [ -z "$identity" ]; then
    identity="-"
fi

codesign \
    --sign "$identity" \
    --force \
    --entitlements "$entitlements" \
    --identifier com.togodynamics.nooto.sys-audio-capture \
    --options runtime \
    "$out_bin"

echo "signed $out_bin (identity: $identity)"
