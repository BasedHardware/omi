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

# SCA-3883 release identity: stable for the same inputs, sensitive to each of them, and
# refuses rather than guessing.
identity="$chart/release-identity.sh"
other="sha256:$(printf '%064d' 2)"
first="$("$identity" --digest "$digest")"
[[ "$first" == "$("$identity" --digest "$digest")" ]] || { echo 'release identity is not stable' >&2; exit 1; }
[[ "$first" == *"\"backend_go_tree\":\"$(git -C "$chart" rev-parse HEAD:backend-go)\""* ]] ||
  { echo 'release identity does not report the backend-go tree' >&2; exit 1; }
rendered_of() { sed -E 's/.*"rendered_sha256":"([a-f0-9]{64})".*/\1/' <<<"$1"; }
[[ "$(rendered_of "$first")" != "$(rendered_of "$("$identity" --digest "$other")")" ]] ||
  { echo 'release identity ignores the digest' >&2; exit 1; }
release_values="$(mktemp)"
trap 'rm -f "$release_values"' EXIT
printf 'intake:\n  enabled: true\n  hostname: workerd.example.com\n  addressName: workerd-test-ip\n  tlsSecretName: workerd-test-tls\n  audience: https://workerd.example.com\n  caller: producer@based-hardware.iam.gserviceaccount.com\n  firestoreServiceAccount: workerd@based-hardware.iam.gserviceaccount.com\n' > "$release_values"
[[ "$(rendered_of "$first")" != "$(rendered_of "$("$identity" --digest "$digest" -f "$release_values")")" ]] ||
  { echo 'release identity ignores Release values' >&2; exit 1; }
for bad in '--digest sha256:abc' "--digest $digest --ref no-such-ref" "--digest $digest -f /nonexistent.yaml"; do
  # shellcheck disable=SC2086
  if "$identity" $bad >/dev/null 2>&1; then echo "release identity accepted: $bad" >&2; exit 1; fi
done
echo 'workerd chart render and release identity checks passed'
