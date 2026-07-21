# Backend Deploy Rollout Safety

## Immutable production release records

release-record.yml records one immutable production backend vector: the four
Cloud Run services, backend configuration and secrets, backend-listen, pusher,
LLM gateway, and agent proxy. It does not deploy. An operator may manually
dispatch deploy-release-ring.yml with the recorded ID and confirm=deploy-prod;
that workflow shares the deploy-backend-stack-prod lock and validates
no-traffic revisions before traffic mutation. There is no backend beta ring.
This does not change desktop Beta or Stable update-channel pointers.

Use this runbook when a backend deploy may have produced stale runtime, partial traffic shifts, or GKE pods serving an old ReplicaSet. All commands below are read-only unless explicitly marked as a template for a future deploy workflow.
```

Interpretation:

- `desired`, `updated`, and `available` should match for every active deployment.
- `CrashLoopBackOff`, `ImagePullBackOff`, `ErrImagePull`, and `CreateContainerConfigError` are deploy blockers.
- An old ReplicaSet with replicas beyond the threshold means stale runtime may still be serving while the new rollout is unhealthy.
- Recent warning events are summaries only; inspect the named deployment/pod in an operator shell if the report flags a blocker.

## Read Cloud Run traffic state

```bash
python3 backend/scripts/deploy_status_report.py \
  --env prod \
  --project based-hardware \
  --include-cloud-run \
  --cloud-run-service backend \
  --cloud-run-service backend-sync \
  --cloud-run-service backend-integration
```

Interpretation:

- `latest created` must equal `latest ready` before a revision is safe to serve.
- The traffic column is the serving truth. A newly created ready revision with 0% traffic is not live.
- Image fields show the configured image/tag when Cloud Run exposes it through `services describe`; do not treat checked-in config as proof of a live deploy.

## Verify a planned Cloud Run traffic shift

Future deploy workflows should verify traffic immediately after `gcloud run services update-traffic`:

```bash
python3 backend/scripts/deploy_status_report.py \
  --env prod \
  --project based-hardware \
  --include-cloud-run \
  --cloud-run-service backend \
  --expect-cloud-run-traffic backend=backend-abcdef0-1
```

The command fails if the expected revision is not both latest ready and serving 100% traffic.

## Development post-deploy acceptance

After a successful Auto Deploy Backend to Development run, Verify Development
Backend Deployment runs read-only acceptance against the exact deployment run.
It derives the expected Cloud Run revision names and image tag from the source
commit, Actions run ID, and attempt; it then verifies the four Cloud Run
services and the backend-listen GKE Deployment, Service, and ready
EndpointSlice. The evidence artifact contains only revision, image, timeout,
traffic, and rollout metadata—never environment values or secret contents.

To rerun it after a transient GitHub or GCP failure, dispatch the workflow with
the source deployment's full commit SHA, run ID, and attempt number. Do not use
it as a broad health probe: a newer deployment serving in place of that exact
revision is intentionally a failure.

## Secret-first GKE rollout gate

Before restarting any GKE workload that consumes `backend-secrets`, workflows should apply/sync the ExternalSecret, wait for `Ready`, then verify key presence without printing values:

```bash
kubectl -n prod-omi-backend wait \
  externalsecret/prod-omi-backend-external-secret \
  --for=condition=Ready --timeout=120s

kubectl -n prod-omi-backend get secret prod-omi-backend-secrets -o json \
  | python3 backend/scripts/verify_k8s_secret_keys.py \
      ./backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml
```

This checks only key names. It must not decode, log, or store secret values.
