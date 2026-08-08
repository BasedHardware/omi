#!/bin/bash
# Builds the shell with swiftc into an unsigned omi-* .app bundle. No Xcode project,
# no SwiftPM, no signing/notarization. Never touches /Applications/Omi.app or Omi Beta.
# Bundles the real @omi-core/surfaces dist/ into Contents/Resources/surface/ so the
# shell's fixed-port loopback can serve it without an external Node process.
#
# Env:
#   OMI_BUILD_DIR       output dir (default: ./.build)
#   OMI_SURFACES_DIST   path to surfaces dist/ (default: sibling core-foundation checkout)
#   OMI_APP_NAME        bundle folder name without .app (default: omi-core-tasks-shell)
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${OMI_BUILD_DIR:-$here/.build}"
app_name="${OMI_APP_NAME:-omi-core-tasks-shell}"
# Safety: keep scratch bundles visibly separate from production and prevent a
# name from escaping the output directory or becoming an unsafe plist value.
if [[ ! "$app_name" =~ ^omi-[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
  echo "ERROR: OMI_APP_NAME must match ^omi-[A-Za-z0-9][A-Za-z0-9.-]*$ (got '$app_name')" >&2
  exit 1
fi
app="$out/${app_name}.app"

# Resolve shared surface build. Prefer explicit env, then relative workspace
# candidates; no machine-specific absolute fallback is permitted.
default_dist=""
for candidate in \
  "$here/../../../core-foundation/core/packages/surfaces/dist" \
  "$here/../../../../core-foundation/core/packages/surfaces/dist"; do
  if [[ -f "$candidate/index.html" ]]; then
    default_dist="$(cd "$candidate" && pwd)"
    break
  fi
done
if [[ -z "${OMI_SURFACES_DIST:-}" ]]; then
  if [[ -n "$default_dist" && -f "$default_dist/index.html" ]]; then
    OMI_SURFACES_DIST="$default_dist"
  else
    OMI_SURFACES_DIST=""
  fi
fi
if [[ -z "$OMI_SURFACES_DIST" || ! -f "$OMI_SURFACES_DIST/index.html" ]]; then
  echo "ERROR: surfaces dist missing; set OMI_SURFACES_DIST to a dist directory" >&2
  echo "  Run: cd core && pnpm install && pnpm --filter @omi-core/surfaces build" >&2
  exit 1
fi

mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/surface"

node "$here/codegen/generate.mjs" >/dev/null

swiftc -O \
  -target arm64-apple-macosx13.0 \
  -framework AppKit -framework WebKit -framework Network -framework Security -framework LocalAuthentication \
  -o "$app/Contents/MacOS/$app_name" \
  "$here"/shell/Sources/OmiShell/*.swift

# Copy the real shared surface (relative-base Vite build).
rsync -a --delete "$OMI_SURFACES_DIST/" "$app/Contents/Resources/surface/"

cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>${app_name}</string>
  <key>CFBundleDisplayName</key><string>${app_name}</string>
  <key>CFBundleIdentifier</key><string>me.omi.shell.core-tasks.prototype</string>
  <key>CFBundleExecutable</key><string>${app_name}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
echo "built: ${app/#$here/.}"
echo "surface: $OMI_SURFACES_DIST -> Contents/Resources/surface/"
echo "origin: http://127.0.0.1:5290/ (fixed; IndexedDB persists across relaunch)"
