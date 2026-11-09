#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Wno-unused-parameter -fsanitize=undefined -fno-sanitize-recover=all \
  -I"$here/stubs" "$here/test_battery.c" -o "$out/battery"
"$out/battery"
"$out/battery" charger
python3 - "$here/../../src/lib/core/transport.c" "$out/broadcast.inc" <<'PYTHON'
import sys
from pathlib import Path
source = Path(sys.argv[1]).read_text()
start = "void broadcast_battery_level(struct k_work *work_item)\n{"
end = "\n#endif"
assert source.count(start) == 1
block = source[source.index(start):]
Path(sys.argv[2]).write_text(block[:block.index(end)])
PYTHON
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -Wno-unused-parameter -fsanitize=undefined -fno-sanitize-recover=all \
  -I"$out" "$here/test_broadcast.c" -o "$out/broadcast"
"$out/broadcast"
