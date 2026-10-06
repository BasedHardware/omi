#!/usr/bin/env bash
set -euo pipefail
test_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$(cd "$test_dir/../../src" && pwd)"
aad_test_out="$(mktemp -d)"
trap 'rm -rf "$aad_test_out"' EXIT
compiler="${CC:-cc}"
flags=(-std=c99 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer)
"$compiler" "${flags[@]}" -I"$source_dir" "$test_dir/test_policy.c" -o "$aad_test_out/policy"
"$aad_test_out/policy"
"$compiler" "${flags[@]}" -I"$source_dir" "$source_dir/software_vad.c" \
  "$test_dir/test_software_vad.c" -o "$aad_test_out/vad"
"$aad_test_out/vad"
mic_flags=(-DCONFIG_OMI_ENABLE_T5838_AAD=1 -DCONFIG_OMI_ENABLE_OFFLINE_STORAGE=1
  -DCONFIG_OMI_VAD_ABS_THRESHOLD=250 -DCONFIG_OMI_VAD_HOLD_MS=10000 -DCONFIG_OMI_AAD_SETTLE_MS=800)
"$compiler" "${flags[@]}" "${mic_flags[@]}" -DCONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=1 \
  -DCONFIG_OMI_AAD_SILENCE_TIMEOUT_MS=120000 -I"$test_dir/include" \
  -I"$source_dir" -I"$source_dir/lib/core" "$test_dir/test_mic.c" \
  "$source_dir/software_vad.c" -o "$aad_test_out/mic"
"$aad_test_out/mic"
# Compile the actual mic module with connected gate off and storage absent.
# This is a host header seam, NOT an NCS/DT/board integration build.
"$compiler" "${flags[@]}" "${mic_flags[@]}" -UCONFIG_OMI_ENABLE_OFFLINE_STORAGE \
  -fsyntax-only -I"$test_dir/include" -I"$source_dir" -I"$source_dir/lib/core" "$source_dir/mic.c"
"$compiler" "${flags[@]}" "${mic_flags[@]}" -UCONFIG_OMI_ENABLE_OFFLINE_STORAGE \
  -DCONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=1 -DCONFIG_OMI_AAD_SILENCE_TIMEOUT_MS=120000 \
  -fsyntax-only -I"$test_dir/include" -I"$source_dir" -I"$source_dir/lib/core" "$source_dir/mic.c"
