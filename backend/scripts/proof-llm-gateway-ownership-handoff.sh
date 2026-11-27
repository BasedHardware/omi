#!/usr/bin/env bash
# LIFECYCLE: permanent
set -euo pipefail

# Proves the LLM gateway image-ownership repair by running the real deploy script and handoff
# tool against a throwaway cluster that this script creates and deletes:
#   1. clean path: a fresh install, a new tag and a digest roll through the ordinary deploy
#   2. conflict: an image-only kubectl patch makes the next ordinary deploy fail at the
#      server-side apply preflight, before Helm or kubectl changes anything
#   3. handoff: the tool removes the kubectl-patch entry alone; serving image, pod template,
#      generation and the other owners are unchanged, and the ordinary deploy then rolls
#   4. refusal: the tool refuses once kubectl-patch owns more than the image
#
# Needs kwokctl, Helm 4, kubectl, jq and python3. kwokctl starts a real API server on loopback
# whose nodes are simulated. The caller's kubeconfig is never read: the proof talks only to the
# cluster it just created, under a name unique to this run and through the kubeconfig kwokctl
# wrote for it, and it checks that identity before its first write. GKE's BackendConfig CRD is
# stood in for with a schemaless one.
#
# usage: bash backend/scripts/proof-llm-gateway-ownership-handoff.sh [--keep]
#   --keep   leave the cluster and its kubeconfig in place, to inspect a failure

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

usage() {
  echo "usage: bash backend/scripts/proof-llm-gateway-ownership-handoff.sh [--keep]" >&2
  exit 2
}
KEEP=false
if [[ $# -gt 0 ]]; then
  [[ $# -eq 1 && "${1:-}" == "--keep" ]] || usage
  KEEP=true
fi

NAMESPACE=llm-gateway-ownership-proof
NODE="$NAMESPACE-node"
RELEASE=dev-omi-llm-gateway
GSA=proof-gsa@example.iam.gserviceaccount.com
REPOSITORY=gcr.io/based-hardware/llm-gateway
TAG_REPOSITORY=gcr.io/based-hardware-dev/llm-gateway
A="sha256:$(printf 'a%.0s' {1..64})"
B="sha256:$(printf 'b%.0s' {1..64})"
C="sha256:$(printf 'c%.0s' {1..64})"

for tool in kwokctl kubectl helm jq python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "REFUSED: this proof needs '$tool' on PATH" >&2; exit 3; }
done

WORK="$(mktemp -d)"
KUBECONFIG_RUN="$WORK/kubeconfig"
# A name unique to this run tells its cluster apart from any other, including a remote one that
# a local port-forward or proxy serves on loopback.
CLUSTER="llm-gateway-ownership-proof-$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"
CREATED=false

refuse() { # refuse <reason>: the cluster has not been written to
  echo "REFUSED: $*" >&2
  exit 3
}
fail() {
  echo "PROOF FAILED: $*" >&2
  if [[ "$KEEP" == true ]]; then
    echo "cluster $CLUSTER kept for inspection" >&2
  else
    echo "cluster $CLUSTER removed; rerun with --keep to inspect it" >&2
  fi
  exit 1
}
finish() {
  if [[ "$KEEP" == true ]]; then
    echo "cluster $CLUSTER kept; kubeconfig: $KUBECONFIG_RUN" >&2
    echo "remove it with: kwokctl delete cluster --name $CLUSTER" >&2
    return
  fi
  if ! kwokctl delete cluster --name "$CLUSTER" >/dev/null 2>&1 && [[ "$CREATED" == true ]]; then
    echo "WARNING: cluster $CLUSTER was not deleted; remove it with: kwokctl delete cluster --name $CLUSTER" >&2
  fi
  rm -rf "$WORK"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
ok() { echo "  ok: $*"; }
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
declare -F expect expect_same expect_grep >/dev/null

if ! kwokctl create cluster --name "$CLUSTER" --runtime=binary --kubeconfig "$KUBECONFIG_RUN" >"$WORK/kwokctl.log" 2>&1; then
  tail -n 20 "$WORK/kwokctl.log" >&2
  refuse "kwokctl could not create the throwaway cluster"
fi
[[ -s "$KUBECONFIG_RUN" ]] || refuse "kwokctl wrote no kubeconfig for $CLUSTER"
CREATED=true

kc() { kubectl --kubeconfig "$KUBECONFIG_RUN" "$@"; }
count() { # count <resource> [kubectl args...]: how many items the list holds
  kc get "$@" -o json | python3 -c 'import json, sys; print(len(json.load(sys.stdin)["items"]))'
}
require_empty() { # require_empty <resource> [kubectl args...]: a list that cannot be read refuses
  local n
  n="$(count "$@")" || refuse "could not list $1 in $CLUSTER"
  [[ "$n" =~ ^[0-9]+$ ]] || refuse "could not count $1 in $CLUSTER"
  [[ "$n" == 0 ]] || refuse "$CLUSTER has $1, so it is not empty"
}
require_run_cluster() { # read-only; nothing is written before it returns
  local server recorded version namespaces
  kwokctl get clusters 2>/dev/null | grep -qx -- "$CLUSTER" || refuse "kwokctl does not list $CLUSTER"
  [[ "$(kc config view -o json |
    python3 -c 'import json, sys; config = json.load(sys.stdin); print(len(config["clusters"]), len(config["contexts"]))')" == "1 1" ]] ||
    refuse "the kubeconfig kwokctl wrote for $CLUSTER names other clusters as well"
  server="$(kc config view --minify -o jsonpath='{.clusters[0].cluster.server}')" || refuse "could not read $CLUSTER"
  recorded="$(kwokctl get kubeconfig --name "$CLUSTER" >"$WORK/kwokctl-kubeconfig" 2>/dev/null &&
    kubectl --kubeconfig "$WORK/kwokctl-kubeconfig" config view --minify -o jsonpath='{.clusters[0].cluster.server}')" ||
    refuse "kwokctl has no kubeconfig for $CLUSTER"
  [[ -n "$server" && "$server" == "$recorded" ]] || refuse "the kubeconfig in use is not the one kwokctl holds for $CLUSTER"
  case "$server" in
    https://127.0.0.1:*|http://127.0.0.1:*) ;;
    *) refuse "the API server of $CLUSTER is '$server', not loopback" ;;
  esac
  version="$(kc version -o json | python3 -c 'import json, sys; print(json.load(sys.stdin)["serverVersion"]["gitVersion"])')" ||
    refuse "could not read the Kubernetes version of $CLUSTER"
  [[ "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || refuse "$CLUSTER reports '$version', not an upstream Kubernetes build"
  # Only a cluster that holds nothing can be the one this run just created, and nothing in it
  # can be lost by what follows.
  require_empty nodes
  require_empty pods --all-namespaces
  require_empty customresourcedefinitions
  namespaces="$(kc get namespaces -o json |
    python3 -c 'import json, sys; print(" ".join(sorted(i["metadata"]["name"] for i in json.load(sys.stdin)["items"])))')" ||
    refuse "could not list the namespaces of $CLUSTER"
  [[ "$namespaces" == "default kube-node-lease kube-public kube-system" ]] ||
    refuse "$CLUSTER has the namespaces '$namespaces', not only the four empty defaults"
  SERVER="$server"
  echo "## isolation"
  ok "kwokctl lists $CLUSTER, created by this run"
  ok "the kubeconfig in use is the one kwokctl holds for it; API server $server is loopback"
  ok "$version is an upstream Kubernetes build"
  ok "the cluster is empty: 0 nodes, 0 pods, 0 CRDs, namespaces $namespaces"
}
require_run_cluster

# Every later helm and kubectl call, the deploy script's included, goes through a wrapper that
# pins the run's kubeconfig and logs the call, so a failed preflight can be shown to have made
# no write.
mkdir -p "$WORK/bin"
for tool in helm kubectl; do
  real="$(command -v "$tool")"
  cat >"$WORK/bin/$tool" <<EOF
#!/usr/bin/env bash
export KUBECONFIG="$KUBECONFIG_RUN"
printf '%s' "$tool" >> "\$PROOF_CALLS"
for arg in "\$@"; do printf ' %q' "\$arg" >> "\$PROOF_CALLS"; done
printf '\n' >> "\$PROOF_CALLS"
exec "$real" "\$@"
EOF
  chmod +x "$WORK/bin/$tool"
done
export PATH="$WORK/bin:$PATH" PROOF_CALLS="$WORK/calls" KUBECONFIG="$KUBECONFIG_RUN"

kubectl create namespace "$NAMESPACE" >/dev/null
# kwok's controller reports any Node as Ready and its pods as Running, which the rollout wait needs.
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
kubectl apply --server-side -f - >/dev/null <<'CRD'
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
rolled() { # the outcome lines of a deploy
  grep -E 'successfully rolled out|timed out|ERROR|error:' || true
}

echo "## cluster"
echo "Kubernetes $(kubectl version -o json | jq -r '.serverVersion.gitVersion'), $(helm version | head -1)"
echo "API server: $SERVER"

echo "## 1. clean path: ordinary deploy on a fresh namespace"
deploy 1111111 |& rolled
expect "image after fresh install" "$(image)" "$TAG_REPOSITORY:1111111"
deploy 2222222 |& rolled
expect "image after a new tag" "$(image)" "$TAG_REPOSITORY:2222222"
deploy 3333333@"$A" |& rolled
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
deploy 5555555 |& rolled
expect "image after the next ordinary deploy" "$(image)" "$TAG_REPOSITORY:5555555"
expect "image owner after the next ordinary deploy" "$(image_owners)" "helm/Apply"
deploy 6666666@"$C" |& rolled
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

echo "PROOF PASSED"
