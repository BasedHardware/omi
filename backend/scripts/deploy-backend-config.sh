#!/usr/bin/env bash
# Apply the non-secret backend runtime configuration without exposing values.

set -euo pipefail

: "${ENVIRONMENT:?ENVIRONMENT must be set to dev or prod}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_file="$(mktemp)"
trap 'rm -f "$env_file"' EXIT

config_map="$(python3 "$script_dir/render_gke_backend_config.py" --env "$ENVIRONMENT" --format name)"
python3 "$script_dir/render_gke_backend_config.py" --env "$ENVIRONMENT" --format env >"$env_file"

namespace="${ENVIRONMENT}-omi-backend"
key_count="$(wc -l <"$env_file" | tr -d ' ')"

kubectl -n "$namespace" create configmap "$config_map" \
  --from-env-file="$env_file" \
  --dry-run=client \
  -o yaml | kubectl apply -f -

echo "Applied non-secret runtime ConfigMap ${namespace}/${config_map} (${key_count} keys)."
