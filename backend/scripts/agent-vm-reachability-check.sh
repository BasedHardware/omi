#!/usr/bin/env bash
# Hermetic contract check (default) or live GCP verification for agent VM firewall.
#
# Phase 1: hermetic checks only validate deferred IaC shape.
# Live (--live) expects phase-3 rules already applied — do not use until cutover.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RULE_FILE="${ROOT}/charts/agent-vm-firewall/firewall-rule.yaml"

usage() {
  cat <<'EOF'
Usage: backend/scripts/agent-vm-reachability-check.sh [--live PROJECT]

Hermetic (default):
  - validate deferred firewall IaC allows private tcp:8080 before denying public tcp:8080
  - confirm apply script is phase-3 gated

Live (--live, requires gcloud auth) — phase 3 only:
  - describe the applied firewall rules in GCP and enforce the same contract
  - do not run until AGENT_VM_FIREWALL_APPLY_PHASE3 cutover has completed
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
expected_rules = yaml.safe_load(rule_file.read_text())["firewallRules"]


def fail(message: str) -> None:
    raise SystemExit(f"live firewall contract failed: {message}")


def expect_equal(name: str, field: str, actual, expected) -> None:
    if actual != expected:
        fail(f"{name}: {field} expected {expected!r}, got {actual!r}")


def expect_tcp_8080(name: str, live_rule: dict) -> None:
    entries = live_rule.get("allowed") or live_rule.get("denied") or []
    if not any(entry.get("IPProtocol") == "tcp" and "8080" in (entry.get("ports") or []) for entry in entries):
        fail(f"{name}: missing tcp:8080 rule in allowed/denied entries: {entries!r}")


def describe(name: str) -> dict:
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
    return json.loads(raw)

for expected in expected_rules:
    name = expected["name"]
    live = describe(name)
    expect_equal(name, "direction", live.get("direction"), expected["direction"])
    expect_equal(name, "priority", live.get("priority"), expected["priority"])
    expect_equal(name, "sourceRanges", live.get("sourceRanges"), expected["sourceRanges"])
    expect_equal(name, "targetTags", live.get("targetTags"), expected["targetTags"])
    if expected["action"] == "ALLOW":
        if not live.get("allowed"):
            fail(f"{name}: live rule must use allowed[] (ALLOW action)")
    elif expected["action"] == "DENY":
        if not live.get("denied"):
            fail(f"{name}: live rule must use denied[] (DENY action)")
    else:
        fail(f"{name}: unsupported action {expected['action']!r}")
    expect_tcp_8080(name, live)
print(f"live firewall contract ok: {len(expected_rules)} rules (project={project})")
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
