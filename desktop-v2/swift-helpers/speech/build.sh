#!/usr/bin/env bash
# Build and sign the speech-helper Swift sidecar.
#
# Output: swift-helpers/bin/speech-helper
#
# Signed with the same Apple Development identity + entitlements as the
# main Rust binary.  Mirrors scripts/build-sys-audio-helper.sh exactly.

set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$here/../.." && pwd)"

src="$root/swift-helpers/speech/main.swift"
out_dir="$root/swift-helpers/bin"
out_bin="$out_dir/speech-helper"
entitlements="$root/src-tauri/dev.entitlements"

mkdir -p "$out_dir"

# Skip rebuild if output is newer than source.
if [ -x "$out_bin" ] && [ "$out_bin" -nt "$src" ]; then
    echo "speech-helper is up-to-date"
    exit 0
fi

echo "building $out_bin"
swiftc -O \
    -target arm64-apple-macos14.4 \
    -framework AVFoundation \
    -o "$out_bin" \
    "$src"

chmod +x "$out_bin"

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
    --identifier com.togodynamics.nooto.speech-helper \
    --options runtime \
    "$out_bin"

echo "signed $out_bin (identity: $identity)"
