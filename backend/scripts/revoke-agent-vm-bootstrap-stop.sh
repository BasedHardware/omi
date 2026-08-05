#!/usr/bin/env bash
# Remove the transitional direct GCE stop permission after broker-capable
# startup artifacts and proxy leases are serving in both environments.
set -euo pipefail

if [[ "${AGENT_VM_BOOTSTRAP_IAM_REVOKE:-}" != "1" ]]; then
  echo "REFUSED: set AGENT_VM_BOOTSTRAP_IAM_REVOKE=1 to mutate Agent VM IAM." >&2
  exit 1
fi

ROLE_ID="omiAgentVmSelfStop"
for project in based-hardware-dev based-hardware; do
  service_account="omi-agent-vm-bootstrap@${project}.iam.gserviceaccount.com"
  role="projects/${project}/roles/${ROLE_ID}"
  gcloud projects remove-iam-policy-binding "$project" \
    --member="serviceAccount:${service_account}" \
    --role="$role" \
    --all \
    --quiet
  policy_file="$(mktemp)"
  gcloud projects get-iam-policy "$project" --format=json > "$policy_file"
  SERVICE_ACCOUNT="$service_account" ROLE="$role" python3 - "$policy_file" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as policy_stream:
    policy = json.load(policy_stream)
member = f"serviceAccount:{os.environ['SERVICE_ACCOUNT']}"
role = os.environ["ROLE"]
if any(binding.get("role") == role and member in binding.get("members", []) for binding in policy.get("bindings", [])):
    raise SystemExit(f"direct {role} binding remains for {member}")
PY
  rm -f "$policy_file"
  echo "Verified removal of direct Agent VM stop permission for ${service_account} in ${project}."
done
