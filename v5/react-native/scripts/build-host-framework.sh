#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rn_dir="$(cd "$script_dir/.." && pwd)"
repo_dir="$(cd "$rn_dir/../.." && pwd)"
work_dir="$rn_dir/macos/.build-host-framework"
output="$repo_dir/desktop/macos/Desktop/Vendor/OmiV5Runtime.xcframework"
mkdir -p "$work_dir/bundle" "$(dirname "$output")"
export CP_HOME_DIR="${CP_HOME_DIR:-$work_dir/cocoapods}"
# Bun workspaces can hoist react-native-macos without making the local link
# that this existing Podfile expects.
if [ ! -e "$rn_dir/node_modules/react-native-macos" ]; then
  mkdir -p "$rn_dir/node_modules"
  ln -s ../../node_modules/react-native-macos "$rn_dir/node_modules/react-native-macos"
fi

start_time="$(date +%s)"
(
  cd "$rn_dir/macos"
  pod install
)
(
  cd "$rn_dir"
  bunx react-native bundle --platform macos --dev false --entry-file index.js \
    --bundle-output "$work_dir/bundle/main.jsbundle" --assets-dest "$work_dir/bundle"
)

for arch in arm64 x86_64; do
  xcodebuild -workspace "$rn_dir/macos/RnRuntime.xcworkspace" -scheme OmiV5Runtime \
    -configuration Release -sdk macosx -arch "$arch" \
    -derivedDataPath "$work_dir/$arch" \
    CODE_SIGNING_ALLOWED=NO ONLY_ACTIVE_ARCH=NO ARCHS="$arch" build \
    > "$work_dir/xcodebuild-$arch.log" 2>&1 || {
      tail -80 "$work_dir/xcodebuild-$arch.log" >&2
      exit 1
    }
  printf '%s build succeeded; log: %s\n' "$arch" "$work_dir/xcodebuild-$arch.log"
  framework="$work_dir/$arch/Build/Products/Release/OmiV5Runtime.framework"
  test -f "$framework/OmiV5Runtime"
  cp -R "$work_dir/bundle/." "$framework/Resources/"
done
# One macOS library definition must carry both architectures. Xcode rejects
# separate same-platform frameworks passed to -create-xcframework.
universal="$work_dir/universal/OmiV5Runtime.framework"
rm -rf "$universal" "$output"
mkdir -p "$(dirname "$universal")"
ditto "$work_dir/arm64/Build/Products/Release/OmiV5Runtime.framework" "$universal"
lipo -create \
  "$work_dir/arm64/Build/Products/Release/OmiV5Runtime.framework/OmiV5Runtime" \
  "$work_dir/x86_64/Build/Products/Release/OmiV5Runtime.framework/OmiV5Runtime" \
  -output "$work_dir/OmiV5Runtime-universal"
cp "$work_dir/OmiV5Runtime-universal" "$universal/Versions/A/OmiV5Runtime"
xcodebuild -create-xcframework -framework "$universal" -output "$output"
printf 'OmiV5Runtime framework build: %ss; xcframework size: %s bytes\n' \
  "$(( $(date +%s) - start_time ))" "$(du -sk "$output" | awk '{print $1 * 1024}')"
