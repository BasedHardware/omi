#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-${ENV:-}}"
IMAGE_TAG="${IMAGE_TAG:-}"
# Optional role-image opt-in (plan B B2): deploy <IMAGE_REPOSITORY>@<IMAGE_DIGEST>.
# IMAGE_TAG still names the build identity the gateway reports.
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-}"
IMAGE_DIGEST="${IMAGE_DIGEST:-}"
CHART_DIR="${CHART_DIR:-backend/charts/llm-gateway}"
VALUES_FILE="${VALUES_FILE:-}"
NAMESPACE="${NAMESPACE:-}"
RELEASE_NAME="${RELEASE_NAME:-}"
DRY_RUN="${DRY_RUN:-false}"
SKIP_BACKEND_SECRETS="${SKIP_BACKEND_SECRETS:-false}"
LLM_GATEWAY_GSA="${LLM_GATEWAY_GSA:-}"

if [[ -z "$ENVIRONMENT" ]]; then
  echo "ERROR: ENVIRONMENT or ENV is required" >&2
  exit 2
fi
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "ERROR: LLM Gateway environment must be dev or prod" >&2
  exit 2
fi
if [[ -z "$IMAGE_TAG" ]]; then
  echo "ERROR: IMAGE_TAG is required" >&2
  exit 2
fi
if [[ -n "$IMAGE_DIGEST" || -n "$IMAGE_REPOSITORY" ]]; then
  if [[ ! "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ || -z "$IMAGE_REPOSITORY" ]]; then
    echo "ERROR: IMAGE_REPOSITORY and IMAGE_DIGEST=sha256:<64 hex> must be set together" >&2
    exit 2
  fi
fi
if [[ -z "$LLM_GATEWAY_GSA" ]]; then
  echo "ERROR: LLM_GATEWAY_GSA is required for Vertex Workload Identity" >&2
  exit 2
fi
if [[ -z "$VALUES_FILE" ]]; then
  VALUES_FILE="backend/charts/llm-gateway/${ENVIRONMENT}_omi_llm_gateway_values.yaml"
fi
if [[ -z "$NAMESPACE" ]]; then
  NAMESPACE="${ENVIRONMENT}-omi-backend"
fi
if [[ -z "$RELEASE_NAME" ]]; then
  RELEASE_NAME="${ENVIRONMENT}-omi-llm-gateway"
fi

if [[ ! -f "$VALUES_FILE" ]]; then
  echo "ERROR: llm-gateway values file not found: $VALUES_FILE" >&2
  exit 2
fi

python backend/scripts/validate-llm-gateway-env.py \
  "backend/charts/backend-listen/${ENVIRONMENT}_omi_backend_listen_values.yaml" \
  "$VALUES_FILE"

HELM_ARGS=(
  "$RELEASE_NAME"
  "$CHART_DIR"
  -f "$VALUES_FILE"
  --set-string "image.tag=${IMAGE_TAG}"
  --set-string "serviceAccount.annotations.iam\\.gke\\.io/gcp-service-account=${LLM_GATEWAY_GSA}"
)
if [[ -n "$IMAGE_DIGEST" ]]; then
  HELM_ARGS+=(--set "image.repository=${IMAGE_REPOSITORY}" --set-string "image.digest=${IMAGE_DIGEST}")
fi

helm template "${HELM_ARGS[@]}" >/dev/null

# Helm applies through server-side apply as field manager "helm". The same apply
# as a server-side dry-run reports a field another manager owns before any
# release is mutated, so an out-of-band image patch cannot strand the rollout
# halfway through a deploy.
gateway_apply_preflight() {
  local rendered
  rendered="$(mktemp)"
  if ! helm template -n "$NAMESPACE" "${HELM_ARGS[@]}" --show-only templates/deployment.yaml >"$rendered"; then
    rm -f "$rendered"
    echo "ERROR: llm-gateway Deployment could not be rendered for ${RELEASE_NAME}" >&2
    exit 2
  fi
  if ! kubectl -n "$NAMESPACE" apply --server-side --dry-run=server --field-manager=helm -f "$rendered"; then
    rm -f "$rendered"
    echo "ERROR: llm-gateway apply preflight failed for deploy/${RELEASE_NAME} in ${NAMESPACE}; nothing was changed." >&2
    echo "Resolve the field ownership reported above (backend/docs/runbooks/llm-gateway-image-ownership.md) and rerun; do not force the conflict." >&2
    exit 1
  fi
  rm -f "$rendered"
}

gateway_apply_preflight

if [[ "$SKIP_BACKEND_SECRETS" != "true" ]]; then
  env -u CHART_DIR -u VALUES_FILE -u RELEASE_NAME \
    ENVIRONMENT="$ENVIRONMENT" \
    NAMESPACE="$NAMESPACE" \
    DRY_RUN="$DRY_RUN" \
    GCP_PROJECT_ID="${GCP_PROJECT_ID:-}" \
    GKE_CLUSTER="${GKE_CLUSTER:-}" \
    REGION="${REGION:-}" \
    backend/scripts/deploy-backend-secrets.sh
  if [[ "$DRY_RUN" != "true" ]]; then
    sleep 10
  fi
fi

# The presence check is read-only and runs even when SKIP_BACKEND_SECRETS skips the shared reapply.
if [[ "$DRY_RUN" != "true" ]]; then
    # Fail closed before helm rollout if managed Anthropic readiness would 503.
    python3 - "$NAMESPACE" "${ENVIRONMENT}-omi-backend-secrets" <<'PY'
import base64
import json
import subprocess
import sys

namespace, secret_name = sys.argv[1], sys.argv[2]
raw = subprocess.check_output(
    ["kubectl", "-n", namespace, "get", "secret", secret_name, "-o", "json"],
    text=True,
)
data = json.loads(raw).get("data") or {}
required = ("ANTHROPIC_API_KEY", "METRICS_SECRET", "OMI_LLM_GATEWAY_SERVICE_TOKEN")
missing = [key for key in required if key not in data]
if missing:
    print(f"ERROR: {secret_name} missing key(s): {', '.join(missing)}", file=sys.stderr)
    raise SystemExit(1)
empty = [
    key
    for key in required
    if not base64.b64decode(data[key]).decode("utf-8", errors="replace").strip()
]
if empty:
    print(f"ERROR: {secret_name} has empty value(s) for: {', '.join(empty)}", file=sys.stderr)
    raise SystemExit(1)
print(f"Gateway credential keys present and non-empty in {secret_name}")
PY
fi

adopt_for_helm() {
  local kind="$1"
  local name="$2"
  local owner_release
  local owner_namespace

  if ! kubectl -n "$NAMESPACE" get "$kind" "$name" >/dev/null 2>&1; then
    return
  fi

  owner_release="$(kubectl -n "$NAMESPACE" get "$kind" "$name" -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}' 2>/dev/null || true)"
  owner_namespace="$(kubectl -n "$NAMESPACE" get "$kind" "$name" -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-namespace}' 2>/dev/null || true)"
  if [[ -n "$owner_release" && "$owner_release" != "$RELEASE_NAME" ]]; then
    echo "ERROR: $kind/$name is already owned by Helm release $owner_release" >&2
    exit 1
  fi
  if [[ -n "$owner_namespace" && "$owner_namespace" != "$NAMESPACE" ]]; then
    echo "ERROR: $kind/$name is already owned by Helm namespace $owner_namespace" >&2
    exit 1
  fi

  kubectl -n "$NAMESPACE" label "$kind" "$name" app.kubernetes.io/managed-by=Helm --overwrite
  kubectl -n "$NAMESPACE" annotate "$kind" "$name" \
    "meta.helm.sh/release-name=${RELEASE_NAME}" \
    "meta.helm.sh/release-namespace=${NAMESPACE}" \
    --overwrite
}

if [[ "$DRY_RUN" == "true" ]]; then
  echo "llm-gateway render and apply preflight OK for ${RELEASE_NAME} in ${NAMESPACE}"
  exit 0
fi

# The first gateway ingress and BackendConfig may predate Helm ownership. Adopt
# only the chart's known resources so future deploys converge through Helm.
adopt_for_helm ingress "$RELEASE_NAME"
adopt_for_helm backendconfig "${ENVIRONMENT}-llm-gateway-backend-config"

# The shared secrets reapply and the credential check can take a minute; re-check
# so an owner that appeared in that window still fails before Helm touches the release.
gateway_apply_preflight

helm -n "$NAMESPACE" upgrade --install "${HELM_ARGS[@]}"
kubectl -n "$NAMESPACE" rollout status "deploy/${RELEASE_NAME}" --timeout=300s
