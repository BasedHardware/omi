#!/usr/bin/env bash
# Host regression suite for the production gate; no NCS or pendant required.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$here/../../src" \
  "$here/../../src/software_vad.c" "$here/test_software_vad.c" -o "$out/test_software_vad"
"$out/test_software_vad"
