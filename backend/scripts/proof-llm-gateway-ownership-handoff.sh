#!/usr/bin/env bash
# LIFECYCLE: permanent
set -euo pipefail

# Proves the LLM gateway image-ownership repair against the cluster in the current
# kubeconfig by running the real deploy script and handoff tool:
#   1. clean path: a fresh install, a new tag and a digest roll through the ordinary deploy
#   2. conflict: an image-only kubectl patch makes the next ordinary deploy fail at the
#      server-side apply preflight, before Helm or kubectl changes anything
#   3. handoff: the tool removes the kubectl-patch entry alone; serving image, pod template,
#      generation and the other owners are unchanged, and the ordinary deploy then rolls
#   4. refusal: the tool refuses once kubectl-patch owns more than the image
#
# Needs Helm 4, kubectl, jq and python3 on a kwokctl cluster (a real API server whose nodes are
# simulated). Creates and deletes one namespace and one simulated Node. Refuses to run unless the
# API server is on loopback, so it cannot reach a real cluster by accident. GKE's BackendConfig
# CRD is stood in for with a schemaless one.
#
# usage: bash backend/scripts/proof-llm-gateway-ownership-handoff.sh [--keep]

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

NAMESPACE=llm-gateway-ownership-proof
NODE="$NAMESPACE-node"
RELEASE=dev-omi-llm-gateway
GSA=proof-gsa@example.iam.gserviceaccount.com
REPOSITORY=gcr.io/based-hardware/llm-gateway
TAG_REPOSITORY=gcr.io/based-hardware-dev/llm-gateway
A="sha256:$(printf 'a%.0s' {1..64})"
B="sha256:$(printf 'b%.0s' {1..64})"
C="sha256:$(printf 'c%.0s' {1..64})"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() {
  echo "PROOF FAILED: $*" >&2
  echo "namespace $NAMESPACE kept for inspection" >&2
  exit 1
}
expect() { # expect <label> <actual> <expected>
  if [[ "$2" == "$3" ]]; then
    echo "  ok: $1 = $2"
  else
    fail "$1: expected '$3', got '$2'"
  fi
}
expect_same() { # expect_same <label> <before> <after>
  if [[ "$2" == "$3" ]]; then
    echo "  ok: $1 unchanged"
  else
    fail "$1 changed: '$2' -> '$3'"
  fi
}
expect_grep() { # expect_grep <label> <pattern> <file>
  grep -q -- "$2" "$3" || fail "$1: no match for '$2' in $3"
  echo "  ok: $1"
}

server="$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
case "$server" in
  http://127.0.0.1:*|https://127.0.0.1:*|http://localhost:*|https://localhost:*|http://\[::1\]:*|https://\[::1\]:*) ;;
  *) echo "REFUSED: '$server' is not a loopback API server; use an isolated cluster" >&2; exit 3 ;;
esac

# Every helm and kubectl call the scripts make is logged, so a failed preflight can be
# shown to have made no write.
mkdir -p "$WORK/bin"
for tool in helm kubectl; do
  real="$(command -v "$tool")"
  cat >"$WORK/bin/$tool" <<EOF
#!/usr/bin/env bash
printf '%s' "$tool" >> "\$PROOF_CALLS"
for arg in "\$@"; do printf ' %q' "\$arg" >> "\$PROOF_CALLS"; done
printf '\n' >> "\$PROOF_CALLS"
exec "$real" "\$@"
EOF
  chmod +x "$WORK/bin/$tool"
done
export PATH="$WORK/bin:$PATH" PROOF_CALLS="$WORK/calls"

kubectl delete namespace "$NAMESPACE" --ignore-not-found --wait=true >/dev/null
kubectl create namespace "$NAMESPACE" >/dev/null
# kwok's controller reports any Node as Ready and its pods as Running, which the rollout wait needs.
kubectl delete node "$NODE" --ignore-not-found --wait=true >/dev/null
kubectl apply --server-side -f - >/dev/null <<NODE
apiVersion: v1
kind: Node
metadata:
  labels:
    type: kwok
    kubernetes.io/hostname: $NODE
  name: $NODE
NODE
kubectl wait node "$NODE" --for=condition=Ready --timeout=60s >/dev/null
if ! kubectl api-resources --api-group=cloud.google.com 2>/dev/null | grep -q backendconfigs; then
  kubectl apply --server-side -f - <<'CRD' >/dev/null
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: backendconfigs.cloud.google.com
spec:
  group: cloud.google.com
  names:
    kind: BackendConfig
    plural: backendconfigs
    singular: backendconfig
  scope: Namespaced
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          x-kubernetes-preserve-unknown-fields: true
CRD
fi
kubectl -n "$NAMESPACE" create secret generic dev-omi-backend-secrets \
  --from-literal=ANTHROPIC_API_KEY=proof --from-literal=METRICS_SECRET=proof \
  --from-literal=OMI_LLM_GATEWAY_SERVICE_TOKEN=proof >/dev/null

deploy() { # deploy <tag> | deploy <tag>@<sha256:...>; runs the real deploy script
  local tag="${1%%@*}" digest="" repository=""
  [[ "$1" == *@* ]] && { digest="${1#*@}"; repository="$REPOSITORY"; }
  : >"$PROOF_CALLS"
  ENVIRONMENT=dev NAMESPACE="$NAMESPACE" SKIP_BACKEND_SECRETS=true LLM_GATEWAY_GSA="$GSA" \
    IMAGE_TAG="$tag" IMAGE_REPOSITORY="$repository" IMAGE_DIGEST="$digest" \
    bash backend/scripts/deploy-llm-gateway.sh
}
image() { kubectl -n "$NAMESPACE" get deployment "$RELEASE" -o 'jsonpath={.spec.template.spec.containers[0].image}'; }
generation() { kubectl -n "$NAMESPACE" get deployment "$RELEASE" -o 'jsonpath={.metadata.generation}'; }
image_owners() {
  kubectl -n "$NAMESPACE" get deployment "$RELEASE" --show-managed-fields -o json |
    jq -r '
      [.metadata.managedFields[] | select(.fieldsV1["f:spec"]?["f:template"]?["f:spec"]?["f:containers"]?
        ["k:{\"name\":\"llm-gateway\"}"]?["f:image"]?) | "\(.manager)/\(.operation)"] | join(",")'
}
other_owners() {
  kubectl -n "$NAMESPACE" get deployment "$RELEASE" --show-managed-fields -o json |
    jq -S -c '[.metadata.managedFields[] | select(.manager != "kubectl-patch")]'
}
revisions() { helm -n "$NAMESPACE" history "$RELEASE" -o json | jq -c '[.[] | {revision, status}]'; }
adopted() { # ingress and BackendConfig labels + annotations, which adopt_for_helm rewrites
  kubectl -n "$NAMESPACE" get "ingress/$RELEASE" backendconfig/dev-llm-gateway-backend-config \
    -o 'jsonpath={range .items[*]}{.metadata.labels}{" "}{.metadata.annotations}{"\n"}{end}'
}
handoff() { # handoff [--apply] [--next-deployment <file>]
  python3 backend/scripts/handoff-llm-gateway-image-ownership.py --namespace "$NAMESPACE" --deployment "$RELEASE" "$@"
}

echo "## cluster"
echo "Kubernetes $(kubectl version -o json | jq -r '.serverVersion.gitVersion'), $(helm version | head -1)"
echo "API server: $server"

echo "## 1. clean path: ordinary deploy on a fresh namespace"
deploy 1111111 |& tail -3
expect "image after fresh install" "$(image)" "$TAG_REPOSITORY:1111111"
deploy 2222222 |& tail -1
expect "image after a new tag" "$(image)" "$TAG_REPOSITORY:2222222"
deploy 3333333@"$A" |& tail -1
expect "image after a digest" "$(image)" "$REPOSITORY@$A"
expect "image owner on the clean path" "$(image_owners)" "helm/Apply"
expect_grep "deploy runs the server-side apply dry-run under Helm's field manager" \
  "kubectl -n $NAMESPACE apply --server-side --dry-run=server --field-manager=helm -f" "$PROOF_CALLS"
expect "dry-run precedes the release write" \
  "$(awk '/--dry-run=server/{d=NR} /upgrade --install/{print (d && d<NR) ? "yes" : "no"; exit}' "$PROOF_CALLS")" "yes"

echo "## 2. conflicting owner fails the preflight before Helm mutates the gateway"
kubectl -n "$NAMESPACE" patch deployment "$RELEASE" --type=json \
  -p "[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/image\",\"value\":\"$REPOSITORY@$B\"}]" >/dev/null
kubectl -n "$NAMESPACE" rollout status "deploy/$RELEASE" --timeout=120s |& tail -1
expect "image owner after an out-of-band patch" "$(image_owners)" "kubectl-patch/Update"
before_rv="$(kubectl -n "$NAMESPACE" get deployment "$RELEASE" -o 'jsonpath={.metadata.resourceVersion}')"
before_generation="$(generation)"
before_revisions="$(revisions)"
before_adopted="$(adopted)"
if deploy 4444444 >"$WORK/out" 2>"$WORK/err"; then fail "deploy should have failed at the preflight"; fi
cp "$PROOF_CALLS" "$WORK/failed-calls"
grep -E 'conflict|apply preflight failed' "$WORK/err" | cut -c1-200
expect "resourceVersion" "$(kubectl -n "$NAMESPACE" get deployment "$RELEASE" -o 'jsonpath={.metadata.resourceVersion}')" "$before_rv"
expect "generation" "$(generation)" "$before_generation"
expect "serving image" "$(image)" "$REPOSITORY@$B"
expect_same "Helm release revisions (no failed revision recorded)" "$before_revisions" "$(revisions)"
expect_same "ingress and BackendConfig adoption labels" "$before_adopted" "$(adopted)"
echo "helm and kubectl calls made by the failed deploy:"
cut -c1-200 "$WORK/failed-calls" | sed 's/^/    /'
expect "kubectl writes attempted" "$(grep '^kubectl' "$WORK/failed-calls" | grep -vc -- '--dry-run=server' || true)" "0"
expect "helm calls other than template" "$(grep '^helm' "$WORK/failed-calls" | grep -vc '^helm template' || true)" "0"

echo "## 3. bounded ownership handoff"
before_spec="$(kubectl -n "$NAMESPACE" get deployment "$RELEASE" -o json | jq -S -c .spec)"
before_other_owners="$(other_owners)"
# The Deployment the next ordinary rollout applies, rendered as the deploy preflight renders it.
helm template -n "$NAMESPACE" "$RELEASE" backend/charts/llm-gateway \
  -f backend/charts/llm-gateway/dev_omi_llm_gateway_values.yaml \
  --set-string image.tag=5555555 \
  --set-string "serviceAccount.annotations.iam\\.gke\\.io/gcp-service-account=$GSA" \
  --show-only templates/deployment.yaml >"$WORK/next.yaml"
handoff --next-deployment "$WORK/next.yaml"
handoff --next-deployment "$WORK/next.yaml" --apply
expect "serving image after handoff" "$(image)" "$REPOSITORY@$B"
expect "generation after handoff" "$(generation)" "$before_generation"
expect_same "pod template after handoff" "$before_spec" "$(kubectl -n "$NAMESPACE" get deployment "$RELEASE" -o json | jq -S -c .spec)"
expect_same "Helm and controller managed-fields entries after handoff" "$before_other_owners" "$(other_owners)"
expect "image owner after handoff" "$(image_owners)" ""
deploy 5555555 |& tail -1
expect "image after the next ordinary deploy" "$(image)" "$TAG_REPOSITORY:5555555"
expect "image owner after the next ordinary deploy" "$(image_owners)" "helm/Apply"
deploy 6666666@"$C" |& tail -1
expect "image after a digest through the ordinary deploy" "$(image)" "$REPOSITORY@$C"

echo "## 4. refusal: kubectl-patch owning more than the image"
kubectl -n "$NAMESPACE" patch deployment "$RELEASE" --type=json \
  -p "[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/image\",\"value\":\"$REPOSITORY@$B\"},{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/resources/limits/cpu\",\"value\":\"250m\"}]" >/dev/null
kubectl -n "$NAMESPACE" rollout status "deploy/$RELEASE" --timeout=120s |& tail -1
before_rv="$(kubectl -n "$NAMESPACE" get deployment "$RELEASE" -o 'jsonpath={.metadata.resourceVersion}')"
rc=0
handoff >"$WORK/out" 2>"$WORK/err" || rc=$?
expect "handoff exit code" "$rc" "3"
grep REFUSED "$WORK/err"
expect "image owner after the refusal" "$(image_owners)" "kubectl-patch/Update"
expect "resourceVersion after the refusal" \
  "$(kubectl -n "$NAMESPACE" get deployment "$RELEASE" -o 'jsonpath={.metadata.resourceVersion}')" "$before_rv"

if [[ "${1:-}" != "--keep" ]]; then
  kubectl delete "namespace/$NAMESPACE" "node/$NODE" --wait=false |& tail -2
fi
echo "PROOF PASSED"
