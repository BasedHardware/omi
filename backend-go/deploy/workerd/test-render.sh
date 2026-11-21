#!/usr/bin/env bash
set -euo pipefail

chart="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
digest="sha256:$(printf '%064d' 1)"
render() {
  helm template prod-omi-workerd "$chart" --namespace prod-omi-backend \
    -f "$chart/values-prod.yaml" --set-string "image.digest=$digest" \
    --set-string intake.hostname=workerd.example.com \
    --set-string intake.addressName=workerd-test-ip \
    --set-string intake.tlsSecretName=workerd-test-tls \
    --set-string intake.audience=https://workerd.example.com \
    --set-string intake.caller=producer@based-hardware.iam.gserviceaccount.com \
    --set-string intake.firestoreServiceAccount=workerd@based-hardware.iam.gserviceaccount.com "$@"
}

disabled="$(render --set intake.enabled=false,migration.enabled=false)"
enabled="$(render --set intake.enabled=true,migration.enabled=true)"
for fragment in 'kind: Gateway' 'kind: HTTPRoute' 'name: WORKER_EPISODE_INTAKE_AUDIENCE' \
    'name: WORKER_EPISODE_INTAKE_CALLER' 'kind: Job'; do
  if [[ "$disabled" == *"$fragment"* || "$enabled" != *"$fragment"* ]]; then
    echo "Unexpected boolean switch behavior for $fragment" >&2
    exit 1
  fi
done

for switch in intake.enabled migration.enabled; do
  if result="$(render --set-string "$switch=false" 2>&1)" ||
      [[ "$result" != *"$switch:"* || "$result" != *boolean* ]]; then
    echo "Expected a boolean validation error for $switch" >&2
    echo "$result" >&2
    exit 1
  fi
done
