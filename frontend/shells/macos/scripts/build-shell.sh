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

# Stamp the bundle with the source tree the SHELL was compiled from (not to be
# confused with the surfaces-dist stamp already sitting in
# Contents/Resources/surface/omi-build-stamp.json, written by the surfaces
# build for the bundle it served — the two can legitimately differ and are
# never merged; see integration/lib/provenance.mjs).
#
# A build must never fail because provenance failed: git being unavailable (a
# tarball checkout, a shallow CI clone missing objects) is a real, survivable
# case. On any failure the stamp is a distinguishable `unavailable` object,
# never a fabricated value that merely looks like a valid stamp.
repo_root="$(cd "$here/../../.." && pwd)"
provenance_script="$repo_root/integration/lib/provenance.mjs"
shell_stamp="$app/Contents/Resources/omi-build-stamp.json"
# Fallback writer used both when node is entirely absent (message is a fixed
# literal, safe to embed raw) and as a last resort if even the node-based
# writer below somehow fails.
write_unavailable_stamp_raw() {
  printf '{"schema":1,"repo":"core-foundation","artifact":"macos-app","unavailable":"%s"}\n' "$1" > "$shell_stamp"
}
if ! command -v node >/dev/null 2>&1; then
  write_unavailable_stamp_raw "node unavailable at build time"
elif [[ ! -f "$provenance_script" ]]; then
  write_unavailable_stamp_raw "provenance module missing at $provenance_script"
else
  provenance_stderr="$out/.provenance-stderr.$$"
  if node "$provenance_script" --repo core-foundation --artifact macos-app --out "$shell_stamp" >/dev/null 2>"$provenance_stderr"; then
    rm -f "$provenance_stderr"
  else
    # node is known present here, so let it do the JSON escaping of whatever
    # the CLI printed to stderr — never hand-build JSON around untrusted text.
    node -e '
      const fs = require("fs");
      const reason = fs.readFileSync(process.argv[1], "utf8").trim().slice(0, 300) || "unknown error";
      fs.writeFileSync(process.argv[2], JSON.stringify({
        schema: 1, repo: "core-foundation", artifact: "macos-app",
        unavailable: `provenance CLI failed: ${reason}`,
      }) + "\n");
    ' "$provenance_stderr" "$shell_stamp" || write_unavailable_stamp_raw "provenance CLI failed"
    rm -f "$provenance_stderr"
  fi
fi
echo "stamped: ${shell_stamp/#$here/.}"

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
