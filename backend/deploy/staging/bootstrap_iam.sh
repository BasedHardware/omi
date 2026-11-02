#!/usr/bin/env bash
# One-time, human-tier bootstrap of the staging environment in based-hardware-dev
# (contract (i), decision S1). David runs this once with his own gcloud login.
#
#   bash backend/deploy/staging/bootstrap_iam.sh                 # dry run: print every action
#   bash backend/deploy/staging/bootstrap_iam.sh --apply         # do it (idempotent; safe to re-run)
#   bash backend/deploy/staging/bootstrap_iam.sh --verify        # read-only checks of the end state
#
# ROLLBACK (one line; deletes only what this script created, all named staging-*):
#   bash backend/deploy/staging/bootstrap_iam.sh --rollback --apply
#
# What it creates. Every resource is new and named staging-*; no existing dev
# service, dev SA, dev secret, dev bucket, dev queue or dev database is modified.
# The only existing principal that gains anything is the agent identity
# agent-dev-operator@based-hardware-dev, and only on staging resources.
#
#   based-hardware-dev (all new):
#     service accounts   staging-runtime, staging-worker, staging-tasks-invoker, staging-builder
#     Firestore          named database `staging`, nam5, native mode
#     GCS                based-hardware-dev-staging-{sync,batch,mirror} (uniform access,
#                        public-access prevention; mirror has a 14-day delete lifecycle)
#     Artifact Registry  docker repo `staging` (us-central1)
#     Secret Manager     staging-* secrets: fresh random keys (encryption, admin, signing salts),
#                        and copies of dev's vendor test keys (payloads piped, never printed)
#     GKE dev-omi-gke    namespace `staging` + RoleBinding (ClusterRole edit, that namespace only)
#                        for agent-dev-operator
#     Redis (S2)         no cloud resource: Redis runs in-cluster (StatefulSet in namespace
#                        `staging`, deployed by deploy.sh behind an internal LoadBalancer). This
#                        script only generates its password (staging-redis-password) and puts it
#                        in the k8s Secret staging/staging-redis. Staging Cloud Run reaches it by
#                        Direct VPC egress on omi-dev-vpc-1 (same VPC as dev-omi-gke).
#   based-hardware (prod):
#     IAM deny policy    `staging-deny-all` denying the four staging-* SAs on prod services.
#                        Nothing is granted in prod.
#
# Roles granted (all in based-hardware-dev; resource-scoped wherever GCP allows it):
#   staging-runtime        datastore.user ONLY on databases/staging (IAM condition);
#                          logging.logWriter, monitoring.metricWriter, cloudtrace.agent,
#                          aiplatform.user (project); storage.objectAdmin on staging-sync and
#                          staging-batch, objectViewer on staging-mirror; secretAccessor on each
#                          staging-* secret; cloudtasks.enqueuer + viewer on each staging-* queue;
#                          serviceAccountUser + serviceAccountTokenCreator on staging-tasks-invoker
#                          (OIDC task tokens) and TokenCreator on itself (Firebase custom-token signer);
#                          workloadIdentityUser for KSA staging/staging-runtime (listen, pusher)
#   staging-runtime/worker cloudsql.client + cloudsql.instanceUser conditioned to instance staging-jobs,
#                          and IAM database users on it (lane 12's Postgres job store)
#   staging-worker         datastore.user ONLY on databases/staging (IAM condition);
#                          storage.objectCreator on staging-mirror under replays/ only (condition);
#                          storage.objectAdmin on staging-batch, objectViewer on staging-sync and
#                          staging-mirror; secretAccessor on staging-encryption-secret;
#                          logging.logWriter, monitoring.metricWriter; workloadIdentityUser for
#                          KSA staging/staging-worker (batch worker, parakeet, vad)
#   staging-tasks-invoker  run.invoker on Cloud Run services whose name ends in -staging (condition)
#   staging-builder        artifactregistry.writer on repo `staging`; reader on repo gcr.io (base
#                          image); logging.logWriter;
#                          storage.objectViewer on staging-batch (build source)
#   agent-dev-operator     cloudbuild.builds.editor (project; builds run as staging-builder);
#                          run.admin only on services ending in -staging (condition; needed to set
#                          invoker policy); serviceAccountUser on the four staging SAs;
#                          storage.objectAdmin on the three staging buckets (deploy lock, build
#                          source, lane 4's mirror writes); edit in GKE namespace `staging`;
#                          secretAccessor on staging-encryption-secret and staging-admin-key ONLY
#                          (lane 4: mirror re-encryption, synthetic-user replay);
#                          compute.networkUser on subnet omi-us-central1-dev-vpc-1-subnet-1 only
#                          (Direct VPC egress so staging Cloud Run reaches in-cluster Redis;
#                          the agent has compute.subnetworks.get there but not .use)
set -euo pipefail

DEV=based-hardware-dev
PROD=based-hardware
REGION=us-central1
FIRESTORE_LOCATION=nam5
DB=staging
CLUSTER=dev-omi-gke
NAMESPACE=staging
VPC_SUBNET=omi-us-central1-dev-vpc-1-subnet-1
AGENT="agent-dev-operator@${DEV}.iam.gserviceaccount.com"
SA_NAMES=(staging-runtime staging-worker staging-tasks-invoker staging-builder)
BUCKETS=("${DEV}-staging-sync" "${DEV}-staging-batch" "${DEV}-staging-mirror")
AR_REPO=staging
DENY_POLICY_ID=staging-deny-all

# Fresh random secrets (new values; nothing shared with dev or prod).
RANDOM_SECRETS=(
  ENCRYPTION_SECRET ADMIN_KEY METRICS_SECRET LIFECYCLE_EMAIL_SIGNING_SECRET
  MEMORY_V3_CURSOR_SECRET SCREEN_FRAME_SIGNING_SECRET DREAM_AGENT_FEEDBACK_SALT
  OMI_LLM_GATEWAY_SERVICE_TOKEN TELEGRAM_WEBHOOK_SECRET LINQ_WEBHOOK_SECRET
  REDIS_PASSWORD
)
# Copied from dev Secret Manager (dev's vendor test keys). Spend caps live in the overlay env.
DEV_COPY_SECRETS=(
  OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY OPENROUTER_API_KEY GROQ_API_KEY
  SONIOX_API_KEY HUGGINGFACE_TOKEN FIREBASE_API_KEY STT_SERVICE_MODELS
  MODULATE_API_KEY
)
# Deliberately NOT copied: REDIS_DB_HOST/PASSWORD (dev's Redis is prod's), ENCRYPTION_SECRET,
# PINECONE_*, TYPESENSE_*, STRIPE_*, TWILIO_*, APPLE_*, GOOGLE_CLIENT_SECRET, OAuth client
# secrets, SERVICE_ACCOUNT_JSON, and anything else that names a dev or prod data plane.

# Prod services the deny policy covers (staging principals hold no prod roles anyway;
# the deny makes a future accidental grant inert).
DENY_SERVICES=(
  datastore.googleapis.com firestore.googleapis.com storage.googleapis.com
  secretmanager.googleapis.com redis.googleapis.com cloudtasks.googleapis.com
  run.googleapis.com pubsub.googleapis.com bigquery.googleapis.com
  iam.googleapis.com cloudkms.googleapis.com aiplatform.googleapis.com
  container.googleapis.com cloudscheduler.googleapis.com
)

MODE=dry-run
ROLLBACK=0
for arg in "$@"; do
  case "$arg" in
    --apply) MODE=apply ;;
    --verify) MODE=verify ;;
    --rollback) ROLLBACK=1 ;;
    -h | --help)
      sed -n '2,60p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

sa_email() { printf '%s@%s.iam.gserviceaccount.com' "$1" "$DEV"; }
secret_name() { # ENV_NAME -> staging-env-name
  printf 'staging-%s' "$(printf '%s' "$1" | tr '[:upper:]_' '[:lower:]-')"
}

run() {
  if [[ "$MODE" == apply ]]; then
    "$@"
  else
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
  fi
}

# Run, tolerating "already exists" on create so re-runs are idempotent.
run_create() {
  if [[ "$MODE" != apply ]]; then
    run "$@"
    return 0
  fi
  local out
  if ! out="$("$@" 2>&1)"; then
    if grep -qiE 'already exists|ALREADY_EXISTS|409' <<<"$out"; then
      echo "exists: ${*:1:4}"
      return 0
    fi
    echo "$out" >&2
    return 1
  fi
}

# Run, tolerating "not found" on delete so rollback is idempotent.
run_delete() {
  if [[ "$MODE" != apply ]]; then
    run "$@"
    return 0
  fi
  local out
  if ! out="$("$@" 2>&1)"; then
    if grep -qiE 'not found|NOT_FOUND|404|does not exist' <<<"$out"; then
      echo "absent: ${*:1:4}"
      return 0
    fi
    echo "$out" >&2
    return 1
  fi
}

preflight() {
  if [[ "$MODE" == dry-run ]]; then
    echo "mode: dry-run (prints the plan; no gcloud calls)   rollback: $ROLLBACK"
    return 0
  fi
  if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]] || [[ -n "${GCP_AGENT_TIER:-}" && "${GCP_AGENT_TIER}" != human ]]; then
    echo "refusing: an agent tier is active (GCP_AGENT_TIER=${GCP_AGENT_TIER:-}); run with David's human login" >&2
    echo "  e.g. in a fresh shell: source ~/.local/bin/gcp-agent-env.sh human" >&2
    exit 1
  fi
  local account
  account="$(gcloud config get-value account 2>/dev/null || true)"
  if [[ -z "$account" || "$account" == *.iam.gserviceaccount.com ]]; then
    echo "refusing: active gcloud account '$account' is not a human login" >&2
    exit 1
  fi
  echo "account: $account   mode: $MODE   rollback: $ROLLBACK"
}

copy_dev_secret() { # ENV_NAME: dev secret ENV_NAME -> staging-env-name, payload never printed
  local src="$1" dst
  dst="$(secret_name "$1")"
  run_create gcloud secrets create "$dst" --project="$DEV" --replication-policy=automatic \
    --labels=env=staging,source=dev-copy
  if [[ "$MODE" != apply ]]; then
    echo "[dry-run] gcloud secrets versions access latest --secret=$src --project=$DEV | gcloud secrets versions add $dst --data-file=-"
    return 0
  fi
  if gcloud secrets versions list "$dst" --project="$DEV" --filter=state=ENABLED --format='value(name)' --limit=1 | grep -q .; then
    echo "has version: $dst"
    return 0
  fi
  if ! gcloud secrets describe "$src" --project="$DEV" >/dev/null 2>&1; then
    echo "WARN: dev secret $src missing; $dst left without a version" >&2
    return 0
  fi
  gcloud secrets versions access latest --secret="$src" --project="$DEV" |
    gcloud secrets versions add "$dst" --project="$DEV" --data-file=- >/dev/null
  echo "copied: $src -> $dst"
}

random_secret() { # ENV_NAME: new 48-byte random payload, never printed
  local dst
  dst="$(secret_name "$1")"
  run_create gcloud secrets create "$dst" --project="$DEV" --replication-policy=automatic \
    --labels=env=staging,source=random
  if [[ "$MODE" != apply ]]; then
    echo "[dry-run] openssl rand -base64 48 | gcloud secrets versions add $dst --data-file=-"
    return 0
  fi
  if gcloud secrets versions list "$dst" --project="$DEV" --filter=state=ENABLED --format='value(name)' --limit=1 | grep -q .; then
    echo "has version: $dst"
    return 0
  fi
  openssl rand -base64 48 | tr -d '\n' | gcloud secrets versions add "$dst" --project="$DEV" --data-file=- >/dev/null
  echo "generated: $dst"
}

grant_secret() { # secret-name sa-name
  run gcloud secrets add-iam-policy-binding "$1" --project="$DEV" \
    --member="serviceAccount:$(sa_email "$2")" --role=roles/secretmanager.secretAccessor \
    --condition=None --quiet --format=none
}

project_binding() { # member role [condition-expression title]
  local member="$1" role="$2"
  if [[ $# -ge 4 ]]; then
    run gcloud projects add-iam-policy-binding "$DEV" --member="$member" --role="$role" \
      --condition="expression=$3,title=$4" --quiet --format=none
  else
    run gcloud projects add-iam-policy-binding "$DEV" --member="$member" --role="$role" \
      --condition=None --quiet --format=none
  fi
}

bucket_binding() { # bucket member role
  run gcloud storage buckets add-iam-policy-binding "gs://$1" --member="$2" --role="$3" --quiet --format=none
}

sa_binding() { # target-sa-name member role
  run gcloud iam service-accounts add-iam-policy-binding "$(sa_email "$1")" --project="$DEV" \
    --member="$2" --role="$3" --quiet --format=none
}

write_deny_policy_file() {
  local file="$1" principals="" perms="" sa svc
  for sa in "${SA_NAMES[@]}"; do
    principals+="\"principal://iam.googleapis.com/projects/-/serviceAccounts/$(sa_email "$sa")\","
  done
  for svc in "${DENY_SERVICES[@]}"; do
    perms+="\"${svc}/*\","
  done
  cat >"$file" <<EOF
{
  "displayName": "Staging principals have no access to production",
  "rules": [
    {
      "description": "contract (i): staging-* service accounts in ${DEV} are denied on ${PROD}",
      "denyRule": {
        "deniedPrincipals": [${principals%,}],
        "deniedPermissions": [${perms%,}]
      }
    }
  ]
}
EOF
}

with_dev_kubeconfig() { # runs "$@" with a private kubeconfig for the dev cluster, explicit context
  local kc
  kc="$(mktemp -t staging-kubeconfig.XXXXXX)"
  # Explicit cleanup, not a RETURN trap: the trap outlives this function and fires under set -u
  # after the local is gone ("kc: unbound variable").
  local rc=0
  KUBECONFIG="$kc" gcloud container clusters get-credentials "$CLUSTER" --region="$REGION" --project="$DEV" >/dev/null || rc=$?
  if [ "$rc" -eq 0 ]; then
    KUBECONFIG="$kc" "$@" --context="gke_${DEV}_${REGION}_${CLUSTER}" || rc=$?
  fi
  rm -f "$kc"
  return "$rc"
}

bootstrap() {
  local sa bucket name queue
  echo "== APIs"
  run gcloud services enable cloudbuild.googleapis.com artifactregistry.googleapis.com \
    firestore.googleapis.com secretmanager.googleapis.com cloudtasks.googleapis.com \
    cloudscheduler.googleapis.com iam.googleapis.com --project="$DEV"

  echo "== service accounts"
  for sa in "${SA_NAMES[@]}"; do
    run_create gcloud iam service-accounts create "$sa" --project="$DEV" \
      --display-name="$sa (staging; contract (i))" \
      --description="Staging only. Zero roles in ${PROD}; denied there by ${DENY_POLICY_ID}."
  done

  echo "== Firestore database '$DB' ($FIRESTORE_LOCATION)"
  run_create gcloud firestore databases create --database="$DB" --location="$FIRESTORE_LOCATION" \
    --type=firestore-native --project="$DEV"

  echo "== buckets"
  for bucket in "${BUCKETS[@]}"; do
    run_create gcloud storage buckets create "gs://$bucket" --project="$DEV" --location="$REGION" \
      --uniform-bucket-level-access --public-access-prevention
  done
  local lifecycle
  lifecycle="$(mktemp -t staging-lifecycle.XXXXXX)"
  printf '{"rule":[{"action":{"type":"Delete"},"condition":{"age":14}}]}\n' >"$lifecycle"
  run gcloud storage buckets update "gs://${DEV}-staging-mirror" --lifecycle-file="$lifecycle"

  echo "== Artifact Registry repo '$AR_REPO'"
  run_create gcloud artifacts repositories create "$AR_REPO" --project="$DEV" --location="$REGION" \
    --repository-format=docker --description="staging images, tagged by integration SHA"

  echo "== secrets (payloads never printed)"
  for name in "${RANDOM_SECRETS[@]}"; do random_secret "$name"; done
  for name in "${DEV_COPY_SECRETS[@]}"; do copy_dev_secret "$name"; done

  echo "== runtime identity: staging-runtime"
  local rt wk inv bld
  rt="serviceAccount:$(sa_email staging-runtime)"
  wk="serviceAccount:$(sa_email staging-worker)"
  inv="serviceAccount:$(sa_email staging-tasks-invoker)"
  bld="serviceAccount:$(sa_email staging-builder)"
  project_binding "$rt" roles/datastore.user \
    "resource.name == \"projects/${DEV}/databases/${DB}\"" "staging-db-only"
  for role in roles/logging.logWriter roles/monitoring.metricWriter roles/cloudtrace.agent roles/aiplatform.user; do
    project_binding "$rt" "$role"
  done
  bucket_binding "${DEV}-staging-sync" "$rt" roles/storage.objectAdmin
  bucket_binding "${DEV}-staging-batch" "$rt" roles/storage.objectAdmin
  bucket_binding "${DEV}-staging-mirror" "$rt" roles/storage.objectViewer
  sa_binding staging-tasks-invoker "$rt" roles/iam.serviceAccountUser
  sa_binding staging-tasks-invoker "$rt" roles/iam.serviceAccountTokenCreator
  sa_binding staging-runtime "$rt" roles/iam.serviceAccountTokenCreator
  sa_binding staging-runtime "serviceAccount:${DEV}.svc.id.goog[${NAMESPACE}/staging-runtime]" \
    roles/iam.workloadIdentityUser

  echo "== batch worker identity: staging-worker"
  # The worker leases and publishes batch jobs in the staging database (its Firestore
  # transactions failed closed without this: "transaction has no transaction ID").
  project_binding "$wk" roles/datastore.user \
    "resource.name == \"projects/${DEV}/databases/${DB}\"" "staging-db-only"
  for role in roles/logging.logWriter roles/monitoring.metricWriter; do
    project_binding "$wk" "$role"
  done
  bucket_binding "${DEV}-staging-batch" "$wk" roles/storage.objectAdmin
  bucket_binding "${DEV}-staging-sync" "$wk" roles/storage.objectViewer
  bucket_binding "${DEV}-staging-mirror" "$wk" roles/storage.objectViewer
  # Lane 4's replay Job (KSA staging-worker) writes its aggregate results under replays/ only.
  run gcloud storage buckets add-iam-policy-binding "gs://${DEV}-staging-mirror" --member="$wk" \
    --role=roles/storage.objectCreator \
    --condition="expression=resource.name.startsWith(\"projects/_/buckets/${DEV}-staging-mirror/objects/replays/\"),title=replays-prefix-only" \
    --quiet --format=none
  sa_binding staging-worker "serviceAccount:${DEV}.svc.id.goog[${NAMESPACE}/staging-worker]" \
    roles/iam.workloadIdentityUser

  echo "== secret access"
  for name in "${RANDOM_SECRETS[@]}" "${DEV_COPY_SECRETS[@]}"; do
    grant_secret "$(secret_name "$name")" staging-runtime
  done
  grant_secret "$(secret_name ENCRYPTION_SECRET)" staging-worker
  grant_secret "$(secret_name HUGGINGFACE_TOKEN)" staging-worker
  # Lane 4 (mirror/replay), run on agent-dev-operator: re-encrypt David's mirrored recordings under the
  # staging key, and act as synthetic users through the staging admin key. Secret-level bindings on
  # these two staging secrets only; no other secret, and nothing in dev or prod.
  for name in ENCRYPTION_SECRET ADMIN_KEY; do
    run gcloud secrets add-iam-policy-binding "$(secret_name "$name")" --project="$DEV" \
      --member="serviceAccount:${AGENT}" --role=roles/secretmanager.secretAccessor \
      --condition=None --quiet --format=none
  done

  echo "== Cloud Tasks queue access (queues come from create_queues.sh, run first on dev-operator)"
  if [[ "$MODE" == apply ]]; then
    while IFS= read -r queue; do
      [[ "$queue" == staging-* ]] || continue
      for role in roles/cloudtasks.enqueuer roles/cloudtasks.viewer; do
        gcloud tasks queues add-iam-policy-binding "$queue" --location="$REGION" --project="$DEV" \
          --member="$rt" --role="$role" --quiet --format=none
      done
      echo "queue access: $queue"
    done < <(gcloud tasks queues list --location="$REGION" --project="$DEV" --format='value(name.basename())')
  else
    echo "[dry-run] for each staging-* queue: tasks queues add-iam-policy-binding --member=$rt --role=roles/cloudtasks.{enqueuer,viewer}"
  fi

  echo "== task/scheduler invoker: staging-tasks-invoker"
  project_binding "$inv" roles/run.invoker \
    "resource.name.endsWith(\"-staging\")" "staging-services-only"

  echo "== image builds: staging-builder"
  run gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" --project="$DEV" --location="$REGION" \
    --member="$bld" --role=roles/artifactregistry.writer --quiet --format=none
  project_binding "$bld" roles/logging.logWriter
  # backend/Dockerfile's base image is gcr.io/based-hardware-dev/python:3.11-slim-forky.
  run gcloud artifacts repositories add-iam-policy-binding gcr.io --project="$DEV" --location=us \
    --member="$bld" --role=roles/artifactregistry.reader --quiet --format=none
  bucket_binding "${DEV}-staging-batch" "$bld" roles/storage.objectViewer

  echo "== agent-dev-operator (deploy identity; staging-scoped)"
  local agent="serviceAccount:${AGENT}"
  project_binding "$agent" roles/cloudbuild.builds.editor
  project_binding "$agent" roles/run.admin \
    "resource.name.endsWith(\"-staging\")" "staging-services-only"
  for sa in "${SA_NAMES[@]}"; do
    sa_binding "$sa" "$agent" roles/iam.serviceAccountUser
  done
  for bucket in "${BUCKETS[@]}"; do
    bucket_binding "$bucket" "$agent" roles/storage.objectAdmin
  done

  echo "== GKE namespace '$NAMESPACE' and namespace-scoped RBAC for the agent"
  if [[ "$MODE" == apply ]]; then
    with_dev_kubeconfig kubectl create namespace "$NAMESPACE" 2>/dev/null || echo "exists: namespace $NAMESPACE"
    with_dev_kubeconfig kubectl -n "$NAMESPACE" create rolebinding staging-agent-dev-operator-edit \
      --clusterrole=edit --user="$AGENT" 2>/dev/null || echo "exists: rolebinding"
  else
    echo "[dry-run] kubectl create namespace $NAMESPACE (private KUBECONFIG, explicit context)"
    echo "[dry-run] kubectl -n $NAMESPACE create rolebinding staging-agent-dev-operator-edit --clusterrole=edit --user=$AGENT"
  fi

  echo "== S2 in-cluster Redis: k8s Secret staging/staging-redis from staging-redis-password"
  if [[ "$MODE" == apply ]]; then
    gcloud secrets versions access latest --secret=staging-redis-password --project="$DEV" |
      with_dev_kubeconfig kubectl -n "$NAMESPACE" create secret generic staging-redis \
        --from-file=password=/dev/stdin --dry-run=client -o yaml |
      with_dev_kubeconfig kubectl apply -f - >/dev/null
    echo "k8s secret staging/staging-redis applied"
  else
    echo "[dry-run] secrets versions access staging-redis-password | kubectl -n $NAMESPACE create secret generic staging-redis --from-file=password=/dev/stdin | kubectl apply (never printed)"
  fi
  echo "== Cloud SQL staging-jobs (lane 12 job store): IAM login for staging-runtime and staging-worker"
  # Conditioned to the one instance. The instance itself and the database grants are lane 12's
  # (created on the human tier 10-19); this codifies the identity side so --verify can re-check it.
  local sql_condition="resource.name == \"projects/${DEV}/instances/staging-jobs\""
  for sa in staging-runtime staging-worker; do
    for role in roles/cloudsql.client roles/cloudsql.instanceUser; do
      project_binding "serviceAccount:$(sa_email "$sa")" "$role" "$sql_condition" "staging-jobs-only"
    done
    run_create gcloud sql users create "${sa}@${DEV}.iam" --instance=staging-jobs \
      --type=cloud_iam_service_account --project="$DEV"
  done
  echo "== batch worker: k8s Secret staging/staging-batch-worker (ENCRYPTION_SECRET, HUGGINGFACE_TOKEN)"
  if [[ "$MODE" == apply ]]; then
    local wdir
    wdir="$(mktemp -d -t staging-worker-secret.XXXXXX)"
    chmod 700 "$wdir"
    gcloud secrets versions access latest --secret=staging-encryption-secret --project="$DEV" >"$wdir/ENCRYPTION_SECRET"
    gcloud secrets versions access latest --secret=staging-huggingface-token --project="$DEV" >"$wdir/HUGGINGFACE_TOKEN"
    with_dev_kubeconfig kubectl -n "$NAMESPACE" create secret generic staging-batch-worker \
      --from-file="$wdir/ENCRYPTION_SECRET" --from-file="$wdir/HUGGINGFACE_TOKEN" --dry-run=client -o yaml |
      with_dev_kubeconfig kubectl apply -f - >/dev/null
    rm -rf "$wdir"
    echo "k8s secret staging/staging-batch-worker applied"
  else
    echo "[dry-run] staging-encryption-secret + staging-huggingface-token -> k8s secret staging/staging-batch-worker (temp files 0700, removed; never printed)"
  fi
  echo "== Direct VPC egress for staging Cloud Run (the agent deploys with --network/--subnet)"
  run gcloud compute networks subnets add-iam-policy-binding "$VPC_SUBNET" --region="$REGION" --project="$DEV" \
      --member="serviceAccount:${AGENT}" --role=roles/compute.networkUser --quiet --format=none

  echo "== prod deny policy on $PROD (needs roles/iam.denyAdmin)"
  local deny_file
  deny_file="$(mktemp -t staging-deny.XXXXXX)"
  write_deny_policy_file "$deny_file"
  if [[ "$MODE" == apply ]]; then
    if gcloud iam policies get "$DENY_POLICY_ID" --kind=denypolicies \
      --attachment-point="cloudresourcemanager.googleapis.com/projects/${PROD}" >/dev/null 2>&1; then
      echo "exists: deny policy $DENY_POLICY_ID"
    elif ! gcloud iam policies create "$DENY_POLICY_ID" --kind=denypolicies \
      --attachment-point="cloudresourcemanager.googleapis.com/projects/${PROD}" \
      --policy-file="$deny_file" >/dev/null; then
      echo "WARN: deny policy not created (needs roles/iam.denyAdmin on ${PROD}); staging still holds zero prod roles" >&2
    fi
  else
    echo "[dry-run] gcloud iam policies create $DENY_POLICY_ID --kind=denypolicies --attachment-point=cloudresourcemanager.googleapis.com/projects/${PROD} --policy-file=<generated>"
    sed 's/^/  /' "$deny_file"
  fi
  rm -f "$deny_file" "$lifecycle"
}

rollback() {
  local sa bucket name agent="serviceAccount:${AGENT}"
  echo "== ROLLBACK: removes only staging-* resources and the agent's staging-scoped grants"
  run_delete gcloud iam policies delete "$DENY_POLICY_ID" --kind=denypolicies \
    --attachment-point="cloudresourcemanager.googleapis.com/projects/${PROD}" --quiet
  for name in "${RANDOM_SECRETS[@]}" "${DEV_COPY_SECRETS[@]}"; do
    run_delete gcloud secrets delete "$(secret_name "$name")" --project="$DEV" --quiet
  done
  run_delete gcloud artifacts repositories delete "$AR_REPO" --location="$REGION" --project="$DEV" --quiet
  for bucket in "${BUCKETS[@]}"; do
    run_delete gcloud storage rm -r "gs://$bucket" --quiet
  done
  run_delete gcloud firestore databases delete --database="$DB" --project="$DEV" --quiet
  run_delete gcloud projects remove-iam-policy-binding "$DEV" --member="$agent" \
    --role=roles/cloudbuild.builds.editor --condition=None --quiet --format=none
  run_delete gcloud projects remove-iam-policy-binding "$DEV" --member="$agent" --role=roles/run.admin \
    --condition="expression=resource.name.endsWith(\"-staging\"),title=staging-services-only" --quiet --format=none
  run_delete gcloud compute networks subnets remove-iam-policy-binding "$VPC_SUBNET" --region="$REGION" \
    --project="$DEV" --member="$agent" --role=roles/compute.networkUser --quiet --format=none
  if [[ "$MODE" == apply ]]; then
    with_dev_kubeconfig kubectl delete namespace "$NAMESPACE" --ignore-not-found
  else
    echo "[dry-run] kubectl delete namespace $NAMESPACE (private KUBECONFIG, explicit context)"
  fi
  # Deleting the SAs last; their project-level bindings become deleted:serviceAccount
  # entries, which IAM drops automatically after 30 days.
  for sa in "${SA_NAMES[@]}"; do
    run_delete gcloud iam service-accounts delete "$(sa_email "$sa")" --project="$DEV" --quiet
  done
  echo "rollback complete (staging Cloud Run services / queues are removed by deploy.sh --teardown on dev-operator)"
}

verify() {
  local fail=0 sa member
  echo "== verify: staging principals hold nothing in $PROD"
  member="$(gcloud projects get-iam-policy "$PROD" --format=json |
    python3 -c 'import json,sys; d=json.load(sys.stdin); print("\n".join(m for b in d.get("bindings",[]) for m in b["members"] if "staging-" in m and "based-hardware-dev" in m))')"
  if [[ -n "$member" ]]; then
    echo "FAIL: staging principals bound in $PROD:"
    echo "$member"
    fail=1
  else
    echo "ok: no staging-* bindings in $PROD"
  fi
  if gcloud iam policies get "$DENY_POLICY_ID" --kind=denypolicies \
    --attachment-point="cloudresourcemanager.googleapis.com/projects/${PROD}" >/dev/null 2>&1; then
    echo "ok: deny policy $DENY_POLICY_ID present"
  else
    echo "WARN: deny policy $DENY_POLICY_ID absent"
  fi
  for sa in "${SA_NAMES[@]}"; do
    gcloud iam service-accounts describe "$(sa_email "$sa")" --project="$DEV" >/dev/null 2>&1 &&
      echo "ok: $sa" || {
      echo "FAIL: missing $sa"
      fail=1
    }
  done
  local sql_bound
  sql_bound="$(gcloud projects get-iam-policy "$DEV" --format=json |
    python3 -c 'import json,sys; d=json.load(sys.stdin); print(sum(1 for b in d.get("bindings",[]) if b["role"] in ("roles/cloudsql.client","roles/cloudsql.instanceUser") for m in b["members"] if m.split(":")[-1].split("@")[0] in ("staging-runtime","staging-worker")))')"
  if [[ "$sql_bound" -ge 4 ]]; then echo "ok: cloudsql client+instanceUser for staging-runtime/worker ($sql_bound)"; else
    echo "FAIL: cloudsql bindings for staging-runtime/worker: $sql_bound of 4"
    fail=1
  fi
  # Both runtime and worker transact in the staging DB (10-19: the worker grant was missing and
  # every batch lease failed closed). Each needs datastore.user conditioned to databases/staging.
  local db_bound
  db_bound="$(gcloud projects get-iam-policy "$DEV" --format=json |
    python3 -c 'import json,sys; d=json.load(sys.stdin); print(" ".join(sorted({m.split(":")[-1].split("@")[0] for b in d.get("bindings",[]) if b["role"]=="roles/datastore.user" and "databases/staging" in (b.get("condition") or {}).get("expression","") for m in b["members"]} & {"staging-runtime","staging-worker"})))')"
  if [[ "$db_bound" == "staging-runtime staging-worker" ]]; then echo "ok: datastore.user on databases/staging for staging-runtime and staging-worker"; else
    echo "FAIL: datastore.user on databases/staging only for: ${db_bound:-none} (need staging-runtime and staging-worker)"
    fail=1
  fi
  gcloud firestore databases describe --database="$DB" --project="$DEV" >/dev/null 2>&1 &&
    echo "ok: firestore $DB" || {
    echo "FAIL: firestore $DB missing"
    fail=1
  }
  return "$fail"
}

preflight
if [[ "$MODE" == verify ]]; then
  verify
elif [[ "$ROLLBACK" == 1 ]]; then
  rollback
else
  bootstrap
  echo
  echo "done ($MODE). Next: tell the lane-2 agent; it runs create_queues.sh, indexes and deploy.sh on dev-operator."
fi
