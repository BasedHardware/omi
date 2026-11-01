#!/usr/bin/env bash
# Human tier, once, after deploy.sh has created the *-staging Cloud Run services (contract (i)).
# The conditional project bindings in bootstrap_iam.sh (resource.name.endsWith("-staging")) do not
# take effect for Cloud Run services, so invoker access is granted per service here.
#
#   bash backend/deploy/staging/grant_invokers.sh            # dry run
#   bash backend/deploy/staging/grant_invokers.sh --apply
# Rollback: the same commands with remove-iam-policy-binding (printed by --rollback).
set -euo pipefail
PROJECT=based-hardware-dev
REGION=us-central1
INVOKER="serviceAccount:staging-tasks-invoker@${PROJECT}.iam.gserviceaccount.com"
AGENT="serviceAccount:agent-dev-operator@${PROJECT}.iam.gserviceaccount.com"
MODE=dry-run
VERB=add-iam-policy-binding
for arg in "$@"; do
  case "$arg" in
    --apply) MODE=apply ;;
    --rollback) VERB=remove-iam-policy-binding ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done
run() { if [[ "$MODE" == apply ]]; then "$@"; else printf '[dry-run]'; printf ' %q' "$@"; printf '\n'; fi; }
bind() { # service member role
  run gcloud run services "$VERB" "$1" --region="$REGION" --project="$PROJECT" --member="$2" --role="$3" --quiet --format=none
}
# Public API surface: Firebase-token auth in the app, like prod's backend.
bind backend-staging allUsers roles/run.invoker
for svc in backend-staging backend-sync-staging backend-sync-backfill-staging backend-integration-staging; do
  bind "$svc" "$INVOKER" roles/run.invoker
  # Lets deploy.sh / lane 1 manage these services' IAM later without a human step.
  bind "$svc" "$AGENT" roles/run.admin
done
echo "done ($MODE)"
