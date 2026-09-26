#!/usr/bin/env bash
# Export SwiftPM App Intents metadata and install it in an assembled macOS app.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 <Desktop package dir> <app bundle> <Debug|Release> <arm64|x86_64>" >&2
  exit 2
fi
package_dir="$1"
app_bundle="$2"
configuration="$3"
architecture="$4"
case "$configuration:$architecture" in
  Debug:arm64|Debug:x86_64|Release:arm64|Release:x86_64) ;;
  *) echo "invalid metadata configuration or architecture" >&2; exit 2 ;;
esac

build_root="$package_dir/.build"
[[ -d "$build_root" ]] || { echo "SwiftPM build directory missing: $build_root" >&2; exit 1; }
[[ -d "$app_bundle/Contents/Resources" ]] || { echo "bundle Resources missing: $app_bundle" >&2; exit 1; }
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

# Xcode's SwiftPM backend emits supplementary constant values only for sources
# compiled with -Xswiftc -emit-const-values. Filter to this executable and arch:
# dependency metadata must not be mistaken for Omi's own actions.
find "$build_root" -type f -name '*.swiftconstvalues' \
  -path "*/${configuration}/*/Objects-normal/${architecture}/*" \
  | rg '/(Omi Computer|Omi_Computer)(-p)?\.build/Objects-normal/' \
  | sort > "$work_dir/const-values.list"
[[ -s "$work_dir/const-values.list" ]] || {
  echo "Omi Computer constant-value files missing; build with -Xswiftc -emit-const-values" >&2
  exit 1
}

find "$package_dir/Sources" \
  \( -path "$package_dir/Sources/Theme" -o -path "$package_dir/Sources/OmiSupport" \
     -o -path "$package_dir/Sources/OmiWAL" -o -path "$package_dir/Sources/VoiceTurnDomain" \
     -o -path "$package_dir/Sources/Resources" \) -prune -o \
  -type f -name '*.swift' -print | sort > "$work_dir/sources.list"

xcode_build="$(xcodebuild -version | awk '/Build version/ {print $3}')"
[[ -n "$xcode_build" ]] || { echo "Could not resolve Xcode build number" >&2; exit 1; }
xcrun appintentsmetadataprocessor \
  --output "$work_dir/output" \
  --toolchain-dir "$(xcode-select -p)/Toolchains/XcodeDefault.xctoolchain" \
  --module-name Omi_Computer \
  --sdk-root "$(xcrun --sdk macosx --show-sdk-path)" \
  --xcode-version "$xcode_build" \
  --platform-family macOS \
  --deployment-target 14.0 \
  --target-triple "${architecture}-apple-macos14.0" \
  --source-file-list "$work_dir/sources.list" \
  --swift-const-vals-list "$work_dir/const-values.list" \
  --force

metadata_dir="$work_dir/output/Metadata.appintents"
[[ -s "$metadata_dir/extract.actionsdata" ]] || {
  echo "App Intents processor produced no actions data" >&2
  exit 1
}
python3 - "$metadata_dir/extract.actionsdata" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
for kind, expected in (("actions", "RememberIntent"), ("entities", "ConversationEntity")):
    if expected not in payload.get(kind, {}):
        raise SystemExit(f"App Intents metadata missing {kind} {expected}")
print("App Intents metadata:", ", ".join(sorted(payload["actions"])), "; entities:", ", ".join(sorted(payload["entities"])))
PY
rm -rf "$app_bundle/Contents/Resources/Metadata.appintents"
cp -R "$metadata_dir" "$app_bundle/Contents/Resources/Metadata.appintents"
