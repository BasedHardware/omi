#!/usr/bin/env bash
# Idempotently apply the agent VM public-8080 deny firewall from IaC.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RULE_FILE="${ROOT}/charts/agent-vm-firewall/firewall-rule.yaml"

if [[ ! -f "$RULE_FILE" ]]; then
  echo "ERROR: missing firewall IaC: $RULE_FILE" >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud is required to apply agent VM firewall rules" >&2
  exit 1
fi

read_rule() {
  python3 - "$RULE_FILE" <<'PY'
import sys
from pathlib import Path

import yaml

data = yaml.safe_load(Path(sys.argv[1]).read_text())
required = (
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
missing = [key for key in required if key not in data]
if missing:
    raise SystemExit(f"firewall IaC missing keys: {', '.join(missing)}")
if data["action"] != "DENY":
    raise SystemExit("agent VM firewall contract requires action=DENY")
print(
    data["name"],
    data["project"],
    data["network"],
    data["priority"],
    data["direction"],
    data["action"],
    ",".join(data["sourceRanges"]),
    ",".join(data["targetTags"]),
    data.get("description", ""),
    sep="\t",
)
PY
}

IFS=$'\t' read -r NAME PROJECT NETWORK PRIORITY DIRECTION ACTION SOURCE_RANGES TARGET_TAGS DESCRIPTION < <(read_rule)

RULES_ARGS=()
while IFS= read -r rule; do
  RULES_ARGS+=("$rule")
done < <(
  python3 - "$RULE_FILE" <<'PY'
import sys
from pathlib import Path

import yaml

data = yaml.safe_load(Path(sys.argv[1]).read_text())
for entry in data["rules"]:
    protocol = entry["protocol"]
    ports = entry.get("ports") or []
    if ports:
        print(f"{protocol}:{','.join(ports)}")
    else:
        print(protocol)
PY
)

if gcloud compute firewall-rules describe "$NAME" --project="$PROJECT" >/dev/null 2>&1; then
  echo "updating existing firewall rule $NAME (project=$PROJECT)"
  gcloud compute firewall-rules update "$NAME" \
    --project="$PROJECT" \
    --network="$NETWORK" \
    --priority="$PRIORITY" \
    --direction="$DIRECTION" \
    --action="$ACTION" \
    --rules="$(IFS=,; echo "${RULES_ARGS[*]}")" \
    --source-ranges="$SOURCE_RANGES" \
    --target-tags="$TARGET_TAGS" \
    ${DESCRIPTION:+--description="$DESCRIPTION"}
else
  echo "creating firewall rule $NAME (project=$PROJECT)"
  gcloud compute firewall-rules create "$NAME" \
    --project="$PROJECT" \
    --network="$NETWORK" \
    --priority="$PRIORITY" \
    --direction="$DIRECTION" \
    --action="$ACTION" \
    --rules="$(IFS=,; echo "${RULES_ARGS[*]}")" \
    --source-ranges="$SOURCE_RANGES" \
    --target-tags="$TARGET_TAGS" \
    ${DESCRIPTION:+--description="$DESCRIPTION"}
fi

echo "agent VM firewall applied: $NAME"
