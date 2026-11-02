#!/usr/bin/env bash
# Create or update the staging Cloud Tasks queues in based-hardware-dev (contract (i)).
#
# Tier: dev-operator (`source ~/.local/bin/gcp-agent-env.sh dev-operator`).
# Touches only queues whose names start with `staging-`; never a dev queue.
#
#   backend/deploy/staging/create_queues.sh            # dry run: print the plan
#   backend/deploy/staging/create_queues.sh --apply    # create or update
#
# Rollback (per queue; a deleted queue name cannot be reused for ~7 days):
#   gcloud tasks queues pause staging-<name> --location=us-central1 --project=based-hardware-dev
#
# Rate and retry knobs mirror prod where prod's are declared in the repo
# (.github/actions/deploy-backend-stack, sync-backfill-lifecycle). Lane 7's
# deploy/ops/staging.yaml becomes the source of truth once it lands; this
# script then reads the same numbers.
set -euo pipefail

PROJECT=based-hardware-dev
REGION=us-central1
APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h | --help)
      sed -n '2,13p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

active_project="$(gcloud config get-value project 2>/dev/null || true)"
if [[ "${GCP_AGENT_TIER:-}" != "dev-operator" ]]; then
  echo "refusing: run on the dev-operator tier (GCP_AGENT_TIER=${GCP_AGENT_TIER:-unset})" >&2
  exit 1
fi
if [[ "$active_project" != "$PROJECT" ]]; then
  echo "refusing: active project is '$active_project', expected $PROJECT" >&2
  exit 1
fi

# name | max-concurrent | max-per-second | max-attempts (-1 = unlimited) | min-backoff | max-backoff
QUEUES=(
  "staging-sync-jobs|96|10|5|60s|300s"
  "staging-sync-jobs-fresh|96|10|5|60s|300s"
  "staging-sync-backfill|90|15|-1|5s|60s"
  "staging-sync-backfill-fresh|90|15|-1|5s|60s"
  "staging-batch-quarantine-recovery|4|4|5|5s|60s"
  "staging-enrichment|50|25|-1|10s|300s"
  "staging-provider-stt|16|5|-1|10s|300s"
  "staging-conversation-finalization|16|10|5|5s|60s"
  "staging-audio-merge|16|10|5|5s|60s"
  "staging-account-deletion|4|4|5|5s|300s"
)

existing="$(gcloud tasks queues list --location="$REGION" --project="$PROJECT" --format='value(name.basename())')"

for spec in "${QUEUES[@]}"; do
  IFS='|' read -r name concurrent rate attempts min_backoff max_backoff <<<"$spec"
  case "$name" in
    staging-*) ;;
    *)
      echo "refusing non-staging queue name: $name" >&2
      exit 1
      ;;
  esac
  op=create
  if grep -qx "$name" <<<"$existing"; then
    op=update
  fi
  cmd=(gcloud tasks queues "$op" "$name"
    --location="$REGION" --project="$PROJECT"
    --max-concurrent-dispatches="$concurrent"
    --max-dispatches-per-second="$rate"
    --max-attempts="$attempts"
    --min-backoff="$min_backoff" --max-backoff="$max_backoff")
  if [[ "$APPLY" == 1 ]]; then
    "${cmd[@]}" --quiet >/dev/null
    echo "$op $name: ok"
  else
    echo "[dry-run] ${cmd[*]}"
  fi
done
