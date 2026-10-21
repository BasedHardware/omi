#!/usr/bin/env bash
# One fault-suite flow, executed inside the owned-process supervisor session.
set -uo pipefail

flow_path="${1:?flow path}"
run_dir="${2:?run dir}"
port="${3:?port}"
desktop_dir="${4:?desktop dir}"
flow_name="$(basename "$flow_path" .yaml)"
flow_out="$run_dir/flows/$flow_name"
mkdir -p "$flow_out"

set +e
(
  cd "$desktop_dir"
  python3 scripts/omi-harness run "$flow_path" --lane bridge --port "$port" --out "$flow_out" \
    --allow-legacy-flow-version
)
flow_status=$?
set -e

python3 - "$run_dir/fault-flow-result" "$flow_name" "$flow_status" "$flow_out" <<'PY'
import json
import sys
from pathlib import Path

result_path, name, status, out_dir = sys.argv[1:5]
passed = int(status) == 0
rows = [{
    "name": name,
    "passed": passed,
    "artifacts": str(Path(out_dir).resolve()),
}]
Path(result_path).write_text(("true\n" if passed else "false\n") + json.dumps(rows) + "\n")
PY
