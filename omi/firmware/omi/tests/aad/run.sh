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
# Re-run production mic policy with durable retention: CCC-off may remain in
# AAD, first wake PCM survives without a subscriber, sampled quiet is forwarded.
"$compiler" "${flags[@]}" "${mic_flags[@]}" -DCONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=1 \
  -DCONFIG_OMI_ENABLE_CONNECTED_RETENTION=1 -DCONFIG_OMI_AAD_SILENCE_TIMEOUT_MS=120000 \
  -I"$test_dir/include" -I"$source_dir" -I"$source_dir/lib/core" \
  "$test_dir/test_mic.c" "$source_dir/software_vad.c" "$source_dir/connected_retention.c" -o "$aad_test_out/mic-retention"
"$aad_test_out/mic-retention"
"$compiler" "${flags[@]}" -I"$source_dir" "$test_dir/test_retention.c" \
  "$source_dir/connected_retention.c" -o "$aad_test_out/retention"
"$aad_test_out/retention"
sd_flags=(-DCONFIG_OMI_ENABLE_OFFLINE_STORAGE=1 -I"$test_dir/sd_include"
  -I"$test_dir/include" -I"$source_dir" -I"$source_dir/lib/core")
"$compiler" "${flags[@]}" "${sd_flags[@]}" "$test_dir/test_sd_retention.c" \
  "$source_dir/connected_retention.c" -o "$aad_test_out/sd-retention"
"$aad_test_out/sd-retention"
# Compile unedited production pusher + features handlers with a bounded host
# GATT seam; full registration/DT and concurrent callbacks need the NCS build.
python3 - "$source_dir/lib/core/transport.c" "$aad_test_out" <<'PYSEAM'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
out = Path(sys.argv[2])
out.joinpath("transport_pusher.inc").write_text(
    source[source.index("#define NET_BUFFER_HEADER_SIZE"):source.index("\nint transport_off()")]
)
start = source.rindex("static ssize_t\nfeatures_read_handler(")
out.joinpath("transport_features.inc").write_text(source[start:source.index("\n// --- MTU Update Callback", start)])
PYSEAM
for retained in off on; do
  retention_flags=()
  if [[ "$retained" == on ]]; then retention_flags=(-DCONFIG_OMI_ENABLE_CONNECTED_RETENTION=1); fi
  "$compiler" "${flags[@]}" "${sd_flags[@]}" "${retention_flags[@]}" -I"$aad_test_out" \
    "$test_dir/test_transport_retention.c" "$source_dir/connected_retention.c" \
    -o "$aad_test_out/transport-$retained"
  "$aad_test_out/transport-$retained"
done
# Compile the actual mic module with connected gate off and storage absent.
# This is a host header seam, NOT an NCS/DT/board integration build.
"$compiler" "${flags[@]}" "${mic_flags[@]}" -UCONFIG_OMI_ENABLE_OFFLINE_STORAGE \
  -fsyntax-only -I"$test_dir/include" -I"$source_dir" -I"$source_dir/lib/core" "$source_dir/mic.c"
"$compiler" "${flags[@]}" "${mic_flags[@]}" -UCONFIG_OMI_ENABLE_OFFLINE_STORAGE \
  -DCONFIG_OMI_ENABLE_AAD_CONNECTED_QUIET=1 -DCONFIG_OMI_AAD_SILENCE_TIMEOUT_MS=120000 \
  -fsyntax-only -I"$test_dir/include" -I"$source_dir" -I"$source_dir/lib/core" "$source_dir/mic.c"
