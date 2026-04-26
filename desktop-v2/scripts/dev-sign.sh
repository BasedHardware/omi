#!/usr/bin/env bash
# Sign the dev binary with a real Apple Development certificate (or fall
# back to adhoc) + entitlements + bound Info.plist so macOS TCC treats
# the Core Audio tap calls as a properly identified process.
#
# Ad-hoc signing is NOT enough for Core Audio Process Taps on macOS 14.4+:
# TCC refuses to grant `kTCCServiceAudioCapture` without a stable team
# identifier, and the tap silently delivers zero-filled buffers. The
# Swift desktop app uses the same approach (see `desktop/run.sh:561`).
#
# Override the signing identity via `OMI_SIGN_IDENTITY="Apple Development:
# you@example.com"` if the auto-detected one is wrong.

set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$here/.." && pwd)"

binary="$root/src-tauri/target/debug/nooto-desktop-v2"
entitlements="$root/src-tauri/dev.entitlements"

if [ ! -f "$binary" ]; then
    echo "error: binary not found at $binary — build it first" >&2
    exit 1
fi

if [ ! -f "$entitlements" ]; then
    echo "error: entitlements not found at $entitlements" >&2
    exit 1
fi

# Resolve the signing identity. Real cert (Apple Development / Developer
# ID) is required for Core Audio Tap TCC grants — adhoc `-` won't work.
identity="${OMI_SIGN_IDENTITY:-}"
if [ -z "$identity" ]; then
    identity="$(security find-identity -v -p codesigning 2>/dev/null \
        | grep 'Apple Development' | head -1 \
        | sed 's/.*"\(.*\)"/\1/')"
fi
if [ -z "$identity" ]; then
    identity="$(security find-identity -v -p codesigning 2>/dev/null \
        | grep 'Developer ID Application' | head -1 \
        | sed 's/.*"\(.*\)"/\1/')"
fi
if [ -z "$identity" ]; then
    echo "warning: no Apple Development / Developer ID cert found — falling" >&2
    echo "         back to adhoc signing. Core Audio Taps will silently" >&2
    echo "         deliver zero-filled frames. Set OMI_SIGN_IDENTITY or" >&2
    echo "         import a developer cert into the login keychain." >&2
    identity="-"
fi

codesign \
    --sign "$identity" \
    --force \
    --entitlements "$entitlements" \
    --identifier com.togodynamics.nooto \
    --options runtime \
    --timestamp=none \
    "$binary"

echo "signed: $binary (identity: $identity)"
codesign -dv "$binary" 2>&1 | grep -E "^(Identifier|Authority|TeamIdentifier|Info\.plist|Signature)" || true
