#!/usr/bin/env bash
# Deploy an integration SHA to staging in based-hardware-dev (contract (i), decision S3: script, no workflow).
#
#   backend/deploy/staging/deploy.sh <sha> [--services backend,backend-sync,...] [--with-worker]
#                                          [--skip-build] [--allow-non-integration] [--break-lock]
#                                          [--set KEY=VALUE ...] [--warm backend,backend-sync]
#     --set   operator override for a rehearsal window, applied to every deployed service after the
#             overlay render (still fenced, logged by name in the deploy log). Not committed config:
#             re-run without it to restore the overlay values.
#     --warm  min-instances=1 on the named services for the window (default: overlay's 0).
#     --services none   deploy only the batch worker (with --with-worker), e.g. for an A/B arm.
#     --worker-set KEY=VALUE  worker-only rehearsal override (not committed; plain redeploy restores).
#     --no-gmp  skip the Managed Prometheus 'collector' sidecar (default: attached like prod).
#     --worker-probe FILE     run the worker through a staging-only measurement wrapper (ConfigMap
#                             staging-asrctx-probe from FILE); observation only.
#     --worker-replicas N     batch worker replicas to apply (default 0: GPUs on demand, parakeet-pool
#                             min 0). Replay windows pass 2, or scale up before traffic and back to 0 after.
#   Committed worker config: backend/deploy/staging/worker_env.yaml (plain values or secretKeyRef).
#   backend/deploy/staging/deploy.sh --teardown        # delete the *-staging Cloud Run services and the batch worker
#
# Tier: dev-operator only. Only lanes 1 and 2 deploy staging; other lanes ask on the board.
# Order (each step gates the next):
#   1. lock      gs://based-hardware-dev-staging-batch/locks/deploy (generation-match create)
#   2. source    `git archive <sha>` into a temp dir; OMI_RELEASE_TREE = <sha>^{tree}
#   3. fence     the staging fence's negative tests and the staging-mirrors-prod check, run on that tree
#   4. redis     in-cluster Redis applied (namespace staging); its internal LB IP -> REDIS_DB_HOST
#   5. compose   compose_runtime_env.py --env staging (fails on any prod-pointing value)
#   6. build     Cloud Build as staging-builder -> us-central1-docker.pkg.dev/based-hardware-dev/staging/*:<sha>
#   7. deploy    gcloud run deploy <svc>-staging, full declarative env (--env-vars-file, --set-secrets)
#   8. verify    serving revision has 100% traffic and its env equals the rendered env
#                (OMI_BACKEND_RELEASE_SHA=<sha>, OMI_RELEASE_TREE=<tree>); values compared, never printed
#
# Rollback: re-run with the previous good SHA (logged in data/run-2026-10-19-legacy-retire/lane02/deploys.log),
# or `gcloud run services update-traffic <svc>-staging --to-revisions=<rev>=100`.
set -euo pipefail

PROJECT=based-hardware-dev
REGION=us-central1
CLUSTER=dev-omi-gke
NAMESPACE=staging
LOCK="gs://${PROJECT}-staging-batch/locks/deploy"
BUILD_SOURCE_DIR="gs://${PROJECT}-staging-batch/cloudbuild/source"
BUILDER_SA="projects/${PROJECT}/serviceAccounts/staging-builder@${PROJECT}.iam.gserviceaccount.com"
IMAGE_REPO="us-central1-docker.pkg.dev/${PROJECT}/staging"
# Trunk-only since M3 (10-21, ruling 749906): integration/legacy-retire merged into main and was deleted.
STAGING_BASE_BRANCH="${STAGING_DEPLOY_BASE_BRANCH:-main}"
INTEGRATION_REF="origin/${STAGING_BASE_BRANCH}"
ALL_SERVICES=(backend backend-sync backend-sync-backfill backend-integration)
REPO_ROOT="${STAGING_DEPLOY_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
# bash reads a script as it runs; run from a private copy so edits to the checkout cannot mix versions.
if [[ -z "${STAGING_DEPLOY_REEXEC:-}" ]]; then
  self_copy="$(mktemp -t staging-deploy-sh.XXXXXX)"
  cp "${BASH_SOURCE[0]}" "$self_copy"
  STAGING_DEPLOY_REEXEC="$self_copy" STAGING_DEPLOY_REPO_ROOT="$REPO_ROOT" exec bash "$self_copy" "$@"
fi
PY="${REPO_ROOT}/backend/.venv/bin/python"
DEPLOY_LOG="${OMI_STAGING_DEPLOY_LOG:-$HOME/workspace/omi/data/run-2026-10-19-legacy-retire/lane02/deploys.log}"

# Prod-shaped runtime per service (prod live Cloud Run, read 2026-10-19 on ro-prod). Replica counts
# are staging-sized by the overlay; these mirror concurrency, CPU, memory and timeout.
shape_flags() {
  case "$1" in
    backend) echo "--concurrency=20 --cpu=2 --memory=8Gi --timeout=3600 --ingress=all" ;;
    backend-sync) echo "--concurrency=20 --cpu=2 --memory=8Gi --timeout=3600 --ingress=all" ;;
    backend-sync-backfill) echo "--concurrency=6 --cpu=2 --memory=8Gi --timeout=1500 --ingress=all" ;;
    backend-integration) echo "--concurrency=40 --cpu=2 --memory=2Gi --ingress=all" ;;
    *) return 1 ;;
  esac
}
# Invoker policy is not set here: the agent cannot set Cloud Run IAM. grant_invokers.sh (human tier,
# once, after the services exist) grants allUsers on backend-staging (Firebase-token auth like prod's
# backend) and staging-tasks-invoker on every *-staging service. New services start private.

die() {
  echo "deploy.sh: $*" >&2
  exit 1
}
log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }

SHA=""
SERVICES=("${ALL_SERVICES[@]}")
WITH_WORKER=false
SKIP_BUILD=0
ALLOW_NON_INTEGRATION=0
BREAK_LOCK=0
TEARDOWN=0
OVERRIDES=()
WARM=()
WORKER_SETS=()
WORKER_PROBE=""
# GPU on demand (approved 2026-10-20): the worker idles at 0 so parakeet-pool's L4s scale to 0.
WORKER_REPLICAS=0
GMP=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --services)
      IFS=',' read -r -a SERVICES <<<"$2"
      shift
      ;;
    --with-worker) WITH_WORKER=true ;;
    --set)
      [[ "$2" =~ ^[A-Z][A-Z0-9_]*=.*$ ]] || die "--set expects KEY=VALUE"
      OVERRIDES+=("$2")
      shift
      ;;
    --worker-set)
      [[ "$2" =~ ^[A-Z][A-Z0-9_]*=.*$ ]] || die "--worker-set expects KEY=VALUE"
      WORKER_SETS+=("$2")
      shift
      ;;
    --worker-replicas)
      [[ "$2" =~ ^[0-2]$ ]] || die "--worker-replicas expects 0..2 (parakeet-pool: max 1 L4 per zone, 2 zones)"
      WORKER_REPLICAS="$2"
      shift
      ;;
    --worker-probe)
      [[ -f "$2" ]] || die "--worker-probe file not found: $2"
      WORKER_PROBE="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
      shift
      ;;
    --warm)
      IFS=',' read -r -a WARM <<<"$2"
      shift
      ;;
    --skip-build) SKIP_BUILD=1 ;;
    --no-gmp) GMP=0 ;;
    --allow-non-integration) ALLOW_NON_INTEGRATION=1 ;;
    --break-lock) BREAK_LOCK=1 ;;
    --teardown) TEARDOWN=1 ;;
    -h | --help)
      sed -n '2,26p' "$0"
      exit 0
      ;;
    -*)
      echo "unknown flag: $1" >&2
      exit 2
      ;;
    *) SHA="$1" ;;
  esac
  shift
done


[[ "${GCP_AGENT_TIER:-}" == dev-operator ]] || die "run on the dev-operator tier (source ~/.local/bin/gcp-agent-env.sh dev-operator)"
[[ "$(gcloud config get-value project 2>/dev/null)" == "$PROJECT" ]] || die "active project must be $PROJECT"
if [[ "${SERVICES[*]}" == none ]]; then
  SERVICES=()
  [[ "$WITH_WORKER" == true ]] || die "--services none needs --with-worker"
fi
for svc in "${SERVICES[@]}"; do shape_flags "$svc" >/dev/null || die "unknown service $svc"; done

WORK="$(mktemp -d -t staging-deploy.XXXXXX)"
KUBECONFIG_FILE="$WORK/kubeconfig"
LOCK_HELD=0
cleanup() {
  if [[ "$LOCK_HELD" == 1 ]]; then
    gcloud storage rm "$LOCK" --quiet >/dev/null 2>&1 || echo "WARN: could not release $LOCK" >&2
  fi
  rm -rf "$WORK"
  [[ -f "${STAGING_DEPLOY_REEXEC:-}" ]] && rm -f "$STAGING_DEPLOY_REEXEC"
  # Clear the GKE auth plugin cache this run may have populated (memory: cache crosses tiers).
  rm -rf "${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}/gke_gcloud_auth_plugin_cache" 2>/dev/null || true
}
trap cleanup EXIT

kubectl_staging() {
  if [[ ! -s "$KUBECONFIG_FILE" ]]; then
    KUBECONFIG="$KUBECONFIG_FILE" gcloud container clusters get-credentials "$CLUSTER" --region="$REGION" --project="$PROJECT" >/dev/null
  fi
  KUBECONFIG="$KUBECONFIG_FILE" kubectl --context="gke_${PROJECT}_${REGION}_${CLUSTER}" -n "$NAMESPACE" "$@"
}

acquire_lock() {
  local holder
  holder="${USER:-agent}@$(hostname -s) sha=${SHA:-teardown} $(date -u +%FT%TZ)"
  if [[ "$BREAK_LOCK" == 1 ]]; then
    log "breaking lock: $(gcloud storage cat "$LOCK" 2>/dev/null || echo none)"
    gcloud storage rm "$LOCK" --quiet >/dev/null 2>&1 || true
  fi
  if ! printf '%s\n' "$holder" | gcloud storage cp - "$LOCK" --if-generation-match=0 >/dev/null 2>&1; then
    die "staging deploy lock held: $(gcloud storage cat "$LOCK" 2>/dev/null || echo unreadable) (one deploy at a time; --break-lock if stale)"
  fi
  LOCK_HELD=1
  log "lock acquired"
}

if [[ "$TEARDOWN" == 1 ]]; then
  acquire_lock
  kubectl_staging delete deployment staging-batch-pipeline-worker --ignore-not-found >/dev/null && log "worker deleted (if present)"
  for svc in "${ALL_SERVICES[@]}"; do
    gcloud run services delete "${svc}-staging" --region="$REGION" --project="$PROJECT" --quiet 2>/dev/null &&
      log "deleted ${svc}-staging" || log "absent ${svc}-staging"
  done
  exit 0
fi

[[ -n "$SHA" ]] || die "usage: deploy.sh <sha> [...]"
cd "$REPO_ROOT"
GIT_SSH_COMMAND="ssh -4" git fetch -q origin "$STAGING_BASE_BRANCH" || die "fetch $STAGING_BASE_BRANCH failed"
SHA="$(git rev-parse --verify "${SHA}^{commit}")"
if [[ "$ALLOW_NON_INTEGRATION" != 1 ]] && ! git merge-base --is-ancestor "$SHA" "$INTEGRATION_REF"; then
  die "$SHA is not on $INTEGRATION_REF (staging deploys $STAGING_BASE_BRANCH SHAs; --allow-non-integration for a lane rehearsal)"
fi
TREE="$(git rev-parse "${SHA}^{tree}")"
SHORT="${SHA:0:12}"

acquire_lock

log "source: git archive $SHORT (tree ${TREE:0:12})"
mkdir -p "$WORK/src"
git archive "$SHA" | tar -x -C "$WORK/src"

log "fence: negative tests + staging-mirrors-prod on the exported tree"
(cd "$WORK/src/backend" && "$PY" -m pytest -q -p no:cacheprovider tests/unit/test_staging_fence.py tests/unit/test_staging_overlay.py >"$WORK/fence-tests.log" 2>&1) ||
  {
    tail -20 "$WORK/fence-tests.log" >&2
    die "staging fence tests failed on $SHORT"
  }
(cd "$WORK/src/backend" && "$PY" scripts/cross_service_checks/staging.py) || die "staging-mirrors-prod failed on $SHORT"

log "redis: apply in-cluster staging-redis"
kubectl_staging apply -f "$WORK/src/backend/deploy/staging/redis.yaml" >/dev/null
# A StatefulSet never replaces a Pending pod from an older template; recreate it so the new one schedules.
if [[ "$(kubectl_staging get pod staging-redis-0 -o jsonpath='{.status.phase}' 2>/dev/null || true)" == Pending ]]; then
  kubectl_staging delete pod staging-redis-0 --wait=false >/dev/null
fi
kubectl_staging rollout status statefulset/staging-redis --timeout=300s >/dev/null
REDIS_HOST=""
for _ in $(seq 1 60); do
  REDIS_HOST="$(kubectl_staging get service staging-redis -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  [[ -n "$REDIS_HOST" ]] && break
  sleep 5
done
[[ -n "$REDIS_HOST" ]] || die "staging-redis internal LB has no IP after 5 min"

log "compose: staging overlay"
COMPOSED="$WORK/staging.composed.yaml"
"$PY" "$WORK/src/backend/deploy/compose_runtime_env.py" --env staging \
  --base "$WORK/src/backend/deploy/runtime_env/_base.yaml" \
  --runtime-env-dir "$WORK/src/backend/deploy/runtime_env" \
  --input "STAGING_REDIS_HOST=$REDIS_HOST" --output "$COMPOSED" >/dev/null

if [[ "$SKIP_BUILD" != 1 ]]; then
  log "build: Cloud Build (backend$([[ "$WITH_WORKER" == true ]] && echo ', batch worker')) as staging-builder"
  source_object="${BUILD_SOURCE_DIR}/${SHA}.tgz"
  # Straight from git: re-tarring the extracted tree on macOS adds AppleDouble ._* files.
  git -C "$REPO_ROOT" archive --format=tar.gz -o "$WORK/src.tgz" "$SHA"
  gcloud storage cp "$WORK/src.tgz" "$source_object" --quiet >/dev/null
  gcloud builds submit --no-source --project="$PROJECT" --region="$REGION" \
    --config="$WORK/src/backend/deploy/staging/cloudbuild.yaml" \
    --substitutions="_SHA=${SHA},_BUILD_WORKER=${WITH_WORKER},_SOURCE=${source_object}" \
    --service-account="$BUILDER_SA" \
    --suppress-logs >/dev/null
fi
# Digest of <repo>/<image>:<sha> from the tag listing (images describe needs containeranalysis rights).
image_digest() {
  gcloud artifacts docker images list "${IMAGE_REPO}/$1" --project="$PROJECT" --include-tags \
    --format='value(tags,version)' 2>/dev/null |
    awk -v sha="$SHA" '{ n = split($1, t, ","); for (i = 1; i <= n; i++) if (t[i] == sha) { print $2; exit } }'
}
BACKEND_DIGEST="$(image_digest backend)"
[[ "$BACKEND_DIGEST" == sha256:* ]] || die "image ${IMAGE_REPO}/backend:${SHA} not found"
IMAGE="${IMAGE_REPO}/backend@${BACKEND_DIGEST}"

verify_service() { # svc deploy_name env_file
  local svc="$1" name="$2" env_file="$3" state
  state="$WORK/${svc}.live.json"
  gcloud run services describe "$name" --region="$REGION" --project="$PROJECT" --format=json >"$state"
  "$PY" - "$state" "$env_file" "$SHA" <<'PYEOF'
import json, sys, yaml
live = json.load(open(sys.argv[1]))
want = yaml.safe_load(open(sys.argv[2]))
sha = sys.argv[3]
status = live['status']
ready = status.get('latestReadyRevisionName')
traffic = {t.get('revisionName'): t.get('percent', 0) for t in status.get('traffic', [])}
problems = []
if status.get('latestCreatedRevisionName') != ready:
    problems.append('latest created revision is not ready')
if traffic.get(ready, 0) != 100:
    problems.append('serving traffic is not 100% on the latest ready revision')
container = live['spec']['template']['spec']['containers'][0]
have = {e['name']: e.get('value', '') for e in container.get('env', []) if 'valueFrom' not in e}
# Cloud Run stores an empty value as a name without a value; an absent empty value is not drift.
missing = sorted(k for k in set(want) - set(have) if str(want[k]) != '')
differ = sorted(k for k in want if k in have and str(have[k]) != str(want[k]))
extra = sorted(k for k in set(have) - set(want) if have[k] != '')
if have.get('OMI_BACKEND_RELEASE_SHA') != sha:
    problems.append('OMI_BACKEND_RELEASE_SHA mismatch')
for label, names in (('missing', missing), ('differs', differ), ('unexpected', extra)):
    if names:
        problems.append(f'env {label}: {", ".join(names[:20])}')
if problems:
    print('; '.join(problems)); sys.exit(1)
print(f'serving {ready} at 100%, env matches ({len(want)} vars)')
PYEOF
}

for svc in "${SERVICES[@]}"; do
  name="$("$PY" "$WORK/src/backend/deploy/staging/render_cloud_run.py" --composed "$COMPOSED" --service "$svc" \
    --env-file /dev/null --release-sha "$SHA" --release-tree "$TREE" --field deploy_name)"
  env_file="$WORK/${svc}.env.yaml"
  flags_file="$WORK/${svc}.flags"
  render_flags=()
  "$PY" "$WORK/src/backend/deploy/staging/render_cloud_run.py" --composed "$COMPOSED" \
    --service "$svc" --env-file "$env_file" --flags-file "$flags_file" \
    --release-sha "$SHA" --release-tree "$TREE" || die "render refused $svc"
  while IFS= read -r line; do [[ -n "$line" ]] && render_flags+=("$line"); done <"$flags_file"
  [[ "${#render_flags[@]}" -gt 0 ]] || die "render produced no flags for $svc"
  if [[ "${#OVERRIDES[@]}" -gt 0 ]]; then
    "$PY" - "$WORK/src/backend" "$env_file" "${OVERRIDES[@]}" <<'PYEOF' || die "override refused for $svc"
import sys, yaml
sys.path.insert(0, sys.argv.pop(1))
from utils.staging_fence import staging_violations
path = sys.argv[1]
env = yaml.safe_load(open(path))
for item in sys.argv[2:]:
    key, value = item.split('=', 1)
    env[key] = value
bad = staging_violations({**env, 'OMI_DEPLOYMENT': 'staging'})
if bad:
    sys.exit('fence refuses override: ' + ', '.join(f'{r}:{n}' for r, n in bad))
open(path, 'w').write(yaml.safe_dump(env, sort_keys=True))
PYEOF
  fi
  for warm in "${WARM[@]}"; do
    [[ "$warm" == "$svc" ]] && render_flags+=("--min-instances=1")
  done
  # shellcheck disable=SC2207  # shape flags are fixed tokens without spaces
  shape=($(shape_flags "$svc"))
  log "deploy: $name @ $SHORT"
  suffix="${SHORT}-$(date -u +%H%M%S)"
  serving="${name}-${suffix}"
  no_traffic=()
  current="$(gcloud run services describe "$name" --region="$REGION" --project="$PROJECT" \
    --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)"
  if [[ "$GMP" == 1 && -n "$current" ]]; then
    # Prod's order: a zero-traffic candidate, the collector attached as the final revision, then traffic.
    gcloud run services update-traffic "$name" --to-revisions="${current}=100" \
      --region="$REGION" --project="$PROJECT" --quiet >/dev/null
    no_traffic=(--no-traffic)
  fi
  gcloud run deploy "$name" --project="$PROJECT" --region="$REGION" --image="$IMAGE" \
    --env-vars-file="$env_file" "${render_flags[@]}" "${shape[@]}" \
    --no-cpu-throttling --cpu-boost --execution-environment=gen2 \
    --labels="env=staging,release-sha=${SHORT}" --revision-suffix="$suffix" "${no_traffic[@]}" \
    --quiet >/dev/null
  if [[ "$GMP" == 1 && -n "$current" ]]; then
    gmp_config=cloud_run_gmp_sync.yaml ingress=backend-1
    [[ "$svc" == backend ]] && gmp_config=cloud_run_gmp_sidecar.yaml
    [[ "$svc" == backend-integration ]] && ingress=backend-integration
    # The attach re-checks the ingress env against what was rendered (names and values stay in $WORK).
    "$PY" -c 'import json, sys, yaml
env = yaml.safe_load(open(sys.argv[1]))
json.dump({"services": {sys.argv[2]: {"env": [{"name": k, "value": str(v)} for k, v in env.items()]}}}, open(sys.argv[3], "w"))' \
      "$env_file" "$name" "$WORK/${svc}.env-state.json"
    "$PY" "$WORK/src/backend/scripts/attach_cloud_run_gmp_sidecar.py" --project="$PROJECT" --region="$REGION" \
      --service="$name" --base-revision="$serving" --final-revision="${serving}-gmp" --ingress-container="$ingress" \
      --config="$WORK/src/backend/deploy/$gmp_config" --config-env --expected-env-state="$WORK/${svc}.env-state.json" \
      >/dev/null || die "GMP sidecar attach failed for $name"
    serving="${serving}-gmp"
  fi
  gcloud run services update-traffic "$name" --to-revisions="${serving}=100" \
    --region="$REGION" --project="$PROJECT" --quiet >/dev/null
  verdict="$(verify_service "$svc" "$name" "$env_file")" || die "verify failed for $name: $verdict"
  log "verify: $name $verdict"
done

if [[ "$WITH_WORKER" == true ]]; then
  # Batch worker on dev's idle GPUs (values file pins the pool). The shared chart is rendered with
  # `helm template` and the staging post-renderer adds the staging identity/fence env, then applied.
  kubectl_staging get secret staging-batch-worker >/dev/null 2>&1 ||
    die "k8s secret staging/staging-batch-worker missing (bootstrap_iam.sh --apply creates it)"
  WORKER_IMAGE="${IMAGE_REPO}/batch-pipeline-worker:${SHA}"
  WORKER_DIGEST="$(image_digest batch-pipeline-worker)"
  [[ "$WORKER_DIGEST" == sha256:* ]] || die "worker image $WORKER_IMAGE not found (build with --with-worker)"
  log "worker: render + apply staging-batch-pipeline-worker @ ${WORKER_DIGEST:0:19} replicas=${WORKER_REPLICAS}"
  post_args=(--env-file "$WORK/src/backend/deploy/staging/worker_env.yaml" --replicas "$WORKER_REPLICAS")
  for item in "${WORKER_SETS[@]}"; do post_args+=(--set "$item"); done
  if [[ -n "$WORKER_PROBE" ]]; then
    kubectl_staging create configmap staging-asrctx-probe --from-file="asrctx_probe.py=${WORKER_PROBE}" \
      --dry-run=client -o yaml | kubectl_staging apply -f - >/dev/null
    post_args+=(--probe-configmap staging-asrctx-probe)
  fi
  helm template staging-batch-pipeline-worker "$WORK/src/backend/charts/batch-pipeline-worker" \
    -f "$WORK/src/backend/charts/batch-pipeline-worker/staging_omi_batch-pipeline-worker_values.yaml" \
    --set "image.digest=${WORKER_DIGEST}" --namespace "$NAMESPACE" |
    "$PY" "$WORK/src/backend/deploy/staging/worker_post_render.py" "${post_args[@]}" >"$WORK/worker.yaml"
  kubectl_staging apply -f "$WORK/worker.yaml" >/dev/null
  kubectl_staging annotate deployment/staging-batch-pipeline-worker --overwrite \
    "omi.ai/release-sha=${SHA}" "omi.ai/release-tree=${TREE}" >/dev/null
  kubectl_staging rollout status deployment/staging-batch-pipeline-worker --timeout=1800s >/dev/null ||
    die "batch worker rollout did not complete in 30 min"
  log "worker: $(kubectl_staging get deployment staging-batch-pipeline-worker -o jsonpath='{.status.readyReplicas}/{.spec.replicas}') ready"
fi

mkdir -p "$(dirname "$DEPLOY_LOG")"
printf '%s sha=%s tree=%s services=%s worker=%s overrides=%s warm=%s worker_sets=%s probe=%s\n' "$(date -u +%FT%TZ)" "$SHA" "$TREE" \
  "$(
    IFS=,
    echo "${SERVICES[*]}"
  )" "$WITH_WORKER" "$(
    IFS=,
    echo "${OVERRIDES[*]%%=*}"
  )" "$(
    IFS=,
    echo "${WARM[*]}"
  )" "$(
    IFS=,
    echo "${WORKER_SETS[*]%%=*}"
  )" "${WORKER_PROBE:+yes}" >>"$DEPLOY_LOG"
log "done: staging serves $SHORT (tree ${TREE:0:12})"
