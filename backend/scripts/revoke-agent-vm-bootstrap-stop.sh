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
    --condition=None \
    --quiet >/dev/null 2>&1 || true
  echo "Removed direct Agent VM stop permission for ${service_account} in ${project}."
done
