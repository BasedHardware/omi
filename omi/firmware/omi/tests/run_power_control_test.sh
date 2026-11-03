#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=undefined -fno-sanitize-recover=all \
  -I"$here/settings_stubs" "$here/test_power_control.c" -o "$out/power"
"$out/power"
python3 - "$here/../src/lib/core/transport.c" "$out/power_off.inc" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
start = "/* BLE power-off worker:"
end = "/* End BLE power-off worker. */"
assert source.count(start) == source.count(end) == 1
Path(sys.argv[2]).write_text(source[source.index(start):source.index(end)])
# Protect the allocated UUID, charging attribute order, and privacy on disconnect.
assert 'BT_UUID_128_ENCODE(0x19B10016,' in source
normal = source[source.index('int transport_start()'):]
assert normal.index('k_thread_start(power_off_thread);') < normal.index('bt_enable(NULL)')
safe = source[source.index('int transport_start_safe(void)'):source.index('// periodic advertising')]
assert 'k_thread_start(' not in safe
attrs = source[source.index('static struct bt_gatt_attr settings_service_attr[]'):]
attrs = attrs[:attrs.index('\n};')]
assert attrs.index('&settings_mute_characteristic_uuid.uuid') < attrs.index('&settings_power_control_characteristic_uuid.uuid')
disconnected = source[source.index('static void _transport_disconnected('):]
disconnected = disconnected[:disconnected.index('\nstatic ')]
assert 'mic_resume(' not in disconnected and 'capture_mute_set(' not in disconnected
PY
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -fsanitize=undefined -fno-sanitize-recover=all \
  -I"$out" "$here/test_power_off_queue.c" -o "$out/power-off"
"$out/power-off"
