# Backend Deploy Rollout Safety

## Production backend deployment

Dispatch `gcp_backend.yml` once with `environment=prod`, `mode=deploy`,
`deploy_targets=all`, and the exact admitted `release_sha`. The selected prod
environment provides the single production approval. The workflow checks
Firestore readiness before mutation, creates and validates no-traffic Cloud Run
candidates, reconciles backend secrets using the script-derived service-account
default, updates the GKE backend surfaces, snapshots Cloud Run traffic before
promotion, restores it after a failed promotion or serving-vector check, and
hard-gates the final serving release vector. There is no release-record bucket,
separate deployer identity, or backend beta ring. This does not change desktop
Beta or Stable update-channel pointers.

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

## Check live Cloud Run env drift against the manifest

`google-github-actions/deploy-cloudrun@v3` merges `env_vars` and `secrets` onto existing Cloud Run services rather than replacing the full environment map. To list live environment variable keys on each Cloud Run service (`backend`, `backend-sync`, `backend-sync-backfill`, `backend-integration`) that are absent from `backend/deploy/runtime_env.yaml`, run the read-only operator drift check:

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
python3 backend/scripts/check_cloud_run_env_drift.py --env prod --project based-hardware
```

Interpretation:

- Output contains **key names only**; literal values and Secret Manager payloads are never read, stored, or printed.
- `Allowlisted live-managed keys` (`LIVE_MANAGED_ENV_ALLOWLIST` in `backend/scripts/check_cloud_run_env_drift.py`) covers keys intentionally managed outside `runtime_env.yaml`: per-revision provenance (`OMI_BACKEND_RELEASE_SHA`) and live-managed canary UID allowlists (`BATCH_PIPELINE_UID_ALLOWLIST`, `FIRST_SUMMARY_UID_ALLOWLIST`, `SYNC_BACKFILL_ORDER_UID_ALLOWLIST`, `FAIR_USE_EXEMPT_UIDS`, `DREAM_AGENT_FULL_CONTEXT_UIDS`). Any feature flag whose allowlist is live-managed must fail safe (deny all at `*_PERCENT=0` when the allowlist key is absent) so a service recreate cannot widen rollout.
- `Unallowlisted live keys missing from manifest` lists keys surviving on the live service only because Cloud Run deploys merge env vars. Promote active runtime config into `backend/deploy/runtime_env/{_base,dev.overlay,prod.overlay}.yaml` (and regenerate `backend/deploy/runtime_env.yaml` with `python3 backend/deploy/compose_runtime_env.py`), or retire dead keys via `forbidden_env` / `--remove-env-vars`.
- `.github/actions/deploy-backend-stack/action.yml` runs `check_cloud_run_env_drift.py` as a non-blocking report step after post-deploy runtime env validation and appends the table to `$GITHUB_STEP_SUMMARY`. Pass `--strict` when running as an enforcing gate.
