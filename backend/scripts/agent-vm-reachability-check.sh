#!/usr/bin/env bash
# Hermetic contract check (default) or live GCP verification for agent VM firewall.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RULE_FILE="${ROOT}/charts/agent-vm-firewall/firewall-rule.yaml"

usage() {
  cat <<'EOF'
Usage: backend/scripts/agent-vm-reachability-check.sh [--live PROJECT]

Hermetic (default):
  - validate firewall IaC denies public tcp:8080 for tag omi-agent-vm

Live (--live, requires gcloud auth):
  - describe the applied firewall rule in GCP and assert the same contract
EOF
}

run_hermetic() {
  python3 -m pytest "${ROOT}/tests/unit/test_agent_vm_firewall_contract.py" -q
}

run_live() {
  local project="$1"
  python3 - "$RULE_FILE" "$project" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

import yaml

rule_file = Path(sys.argv[1])
project = sys.argv[2]
expected = yaml.safe_load(rule_file.read_text())
name = expected["name"]

raw = subprocess.check_output(
    [
        "gcloud",
        "compute",
        "firewall-rules",
        "describe",
        name,
        "--project",
        project,
        "--format=json",
    ],
    text=True,
)
live = json.loads(raw)

assert live.get("direction") == expected["direction"], live.get("direction")
assert live.get("priority") == expected["priority"], live.get("priority")
assert live.get("denied"), "live rule must use denied[] (DENY action)"
denied = live["denied"]
assert any(
    entry.get("IPProtocol") == "tcp" and "8080" in (entry.get("ports") or [])
    for entry in denied
), denied
assert live.get("sourceRanges") == expected["sourceRanges"], live.get("sourceRanges")
assert live.get("targetTags") == expected["targetTags"], live.get("targetTags")
print(f"live firewall contract ok: {name} (project={project})")
PY
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--live" ]]; then
  if [[ $# -ne 2 ]]; then
    echo "ERROR: --live requires GCP_PROJECT_ID" >&2
    usage
    exit 2
  fi
  run_hermetic
  run_live "$2"
else
  if [[ $# -ne 0 ]]; then
    echo "ERROR: unknown arguments: $*" >&2
    usage
    exit 2
  fi
  run_hermetic
fi

echo "agent-vm reachability checks passed"
