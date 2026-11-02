#!/bin/sh
set -eu
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/cv1-ble-tests.XXXXXX")
trap 'rm -f "$tmp/tests"; rmdir "$tmp"' EXIT
trap 'exit 1' HUP INT TERM
swiftc -swift-version 5 "$src/Logic.swift" "$src/Tests.swift" -o "$tmp/tests"
"$tmp/tests"
