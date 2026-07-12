#!/usr/bin/env bash
# Idempotently apply the agent VM port-8080 firewall rules from IaC.
#
# PHASE 3 / DEFERRED: refused unless AGENT_VM_FIREWALL_APPLY_PHASE3 is set.
# See backend/charts/agent-vm-firewall/firewall-rule.yaml for prerequisites.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RULE_FILE="${ROOT}/charts/agent-vm-firewall/firewall-rule.yaml"
APPLY_GATE_VALUE="I_UNDERSTAND_BREAKS_DESKTOP_AND_PROXY"

if [[ ! -f "$RULE_FILE" ]]; then
  echo "ERROR: missing firewall IaC: $RULE_FILE" >&2
  exit 1
fi

if [[ "${AGENT_VM_FIREWALL_APPLY_PHASE3:-}" != "$APPLY_GATE_VALUE" ]]; then
  cat >&2 <<EOF
REFUSED: agent VM public-deny firewall apply is phase-3 / deferred (#7326).

Applying these rules (or removing public NAT) breaks agent-proxy and desktop
connectivity today: VMs are on VPC \`default\`, proxy is on \`omi-prod-vpc-1\`
(no peering), and desktop still calls http://{vmIP}:8080 directly.

Prerequisites before apply:
  1) Route desktop upload/sync through agent-proxy (PR10c)
  2) Allowlist reserved Cloud NAT egress for proxy (or peer/move VMs)
  3) Verify private path end-to-end

To override after those land:
  AGENT_VM_FIREWALL_APPLY_PHASE3=$APPLY_GATE_VALUE \\
    backend/scripts/apply-agent-vm-firewall.sh
EOF
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud is required to apply agent VM firewall rules" >&2
  exit 1
fi

read_rules() {
  python3 - "$RULE_FILE" <<'PY'
import json
import sys
from pathlib import Path

import yaml

RULE_REQUIRED = (
    "name",
    "project",
    "network",
    "priority",
    "direction",
    "action",
    "rules",
    "sourceRanges",
    "targetTags",
)
PRIVATE_RANGES = {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"}


def _rules(data: dict) -> list[dict]:
    rules = data.get("firewallRules")
    if not isinstance(rules, list) or not rules:
        raise SystemExit("firewall IaC must define non-empty firewallRules[]")
    return rules


def _has_tcp_8080(rule: dict) -> bool:
    return any(
        entry.get("protocol") == "tcp" and "8080" in (entry.get("ports") or [])
        for entry in rule.get("rules", [])
    )


def _validate(rule: dict) -> None:
    missing = [key for key in RULE_REQUIRED if key not in rule]
    if missing:
        raise SystemExit(f"firewall IaC rule missing keys: {', '.join(missing)}")
    if rule["direction"] != "INGRESS":
        raise SystemExit(f"{rule['name']}: agent VM firewall contract requires direction=INGRESS")
    if "omi-agent-vm" not in rule["targetTags"]:
        raise SystemExit(f"{rule['name']}: targetTags must include omi-agent-vm")
    if not _has_tcp_8080(rule):
        raise SystemExit(f"{rule['name']}: rules must include tcp:8080")


def _validate_contract(rules: list[dict]) -> None:
    for rule in rules:
        _validate(rule)
    allow_private = [rule for rule in rules if rule["name"] == "omi-agent-vm-allow-private-8080"]
    deny_public = [rule for rule in rules if rule["name"] == "omi-agent-vm-deny-public-8080"]
    if len(allow_private) != 1 or len(deny_public) != 1:
        raise SystemExit("firewall IaC must define one private ALLOW and one public DENY rule")
    allow = allow_private[0]
    deny = deny_public[0]
    if allow["action"] != "ALLOW":
        raise SystemExit("private rule must use action=ALLOW")
    if deny["action"] != "DENY":
        raise SystemExit("public rule must use action=DENY")
    if not PRIVATE_RANGES.issubset(set(allow["sourceRanges"])):
        raise SystemExit("private allow rule must include RFC1918 source ranges")
    if "0.0.0.0/0" not in deny["sourceRanges"]:
        raise SystemExit("public deny rule must include 0.0.0.0/0")
    if int(allow["priority"]) >= int(deny["priority"]):
        raise SystemExit("private allow rule priority must be higher than public deny priority")


data = yaml.safe_load(Path(sys.argv[1]).read_text())
rules = _rules(data)
_validate_contract(rules)
for rule in rules:
    print(json.dumps(rule, separators=(",", ":")))
PY
}

rule_args() {
  python3 - "$1" <<'PY'
import json
import sys

rule = json.loads(sys.argv[1])
args = []
for entry in rule["rules"]:
    protocol = entry["protocol"]
    ports = entry.get("ports") or []
    args.append(f"{protocol}:{','.join(ports)}" if ports else protocol)
print(",".join(args))
PY
}

while IFS= read -r RULE_JSON; do
  NAME=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["name"])' "$RULE_JSON")
  PROJECT=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["project"])' "$RULE_JSON")
  NETWORK=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["network"])' "$RULE_JSON")
  PRIORITY=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["priority"])' "$RULE_JSON")
  DIRECTION=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["direction"])' "$RULE_JSON")
  ACTION=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["action"])' "$RULE_JSON")
  SOURCE_RANGES=$(python3 -c 'import json,sys; print(",".join(json.loads(sys.argv[1])["sourceRanges"]))' "$RULE_JSON")
  TARGET_TAGS=$(python3 -c 'import json,sys; print(",".join(json.loads(sys.argv[1])["targetTags"]))' "$RULE_JSON")
  DESCRIPTION=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("description", ""))' "$RULE_JSON")
  RULES_CSV=$(rule_args "$RULE_JSON")

  GCLOUD_ARGS=(
    "$NAME"
    --project="$PROJECT"
    --network="$NETWORK"
    --priority="$PRIORITY"
    --direction="$DIRECTION"
    --action="$ACTION"
    --rules="$RULES_CSV"
    --source-ranges="$SOURCE_RANGES"
    --target-tags="$TARGET_TAGS"
  )
  if [[ -n "$DESCRIPTION" ]]; then
    GCLOUD_ARGS+=(--description="$DESCRIPTION")
  fi

  if gcloud compute firewall-rules describe "$NAME" --project="$PROJECT" >/dev/null 2>&1; then
    echo "updating existing firewall rule $NAME (project=$PROJECT)"
    gcloud compute firewall-rules update "${GCLOUD_ARGS[@]}"
  else
    echo "creating firewall rule $NAME (project=$PROJECT)"
    gcloud compute firewall-rules create "${GCLOUD_ARGS[@]}"
  fi
done < <(read_rules)

echo "agent VM firewall applied: $RULE_FILE"
