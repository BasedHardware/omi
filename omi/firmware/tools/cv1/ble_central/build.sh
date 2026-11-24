#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then
    echo 'Usage: build.sh NEW_APP_PATH.app (build/sign only; never launches)' >&2
    exit 2
fi
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
app=$1
case "$app" in *.app) ;; *) echo 'Destination must end in .app' >&2; exit 2 ;; esac
# mkdir is exclusive, including dangling symlinks. Never remove an existing bundle.
mkdir -- "$app"
mkdir -- "$app/Contents" "$app/Contents/MacOS"
cp "$src/Info.plist" "$app/Contents/Info.plist"
xcrun swiftc -swift-version 5 -O -framework AppKit -framework CoreBluetooth \
    "$src/Logic.swift" "$src/main.swift" -o "$app/Contents/MacOS/CV1BLECentral"
plutil -lint "$app/Contents/Info.plist"
codesign --force --sign - --timestamp=none "$app"
codesign --verify --strict --verbose=2 "$app"
echo "Built and ad-hoc signed; not launched: $app"
