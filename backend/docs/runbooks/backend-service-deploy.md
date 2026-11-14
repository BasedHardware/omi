# Deploy selected backend Cloud Run services

The release role may dispatch the existing `gcp_backend.yml` from `main` with
`mode=deploy`, `deploy_targets=cloud-run-only`, and `services` set to a comma list
of `backend`, `backend-sync`, `backend-sync-backfill`, and `backend-integration`.
Use exact names with no spaces, duplicate names, or empty entries. For example:

```bash
gh workflow run gcp_backend.yml --ref main \
  -f environment=prod -f mode=deploy -f deploy_targets=cloud-run-only \
  -f requested_by=release:SCA-1898 -f release_sha=<full-merged-main-sha> \
  -f services=backend-integration
```

Blank `services` retains the existing stack behavior. Explicit selection is
rejected for build-only, traffic repair, auto-dev, `deploy_targets=all`, and
combined gateway deployment. Automatic development deploys keep their default
full stack behavior. Deployment still uses the shared environment concurrency
lock, exact main SHA admission, Firestore readiness and the production GitHub
Environment approval. This runbook grants no deployment permission.

Only selected services receive revisions, env/secret updates, legacy public env binding
migration, sidecars, candidate tags, traffic repair or promotion. Unselected
services retain their image, env, traffic, tags, sidecars and IAM bindings.
Explicit selection skips shared queue/IAM/TTL/alert provisioning and all GKE
changes; prerequisites must already exist. A sync-only deploy resolves the
backfill dispatch URL and queue without deploying the backfill worker.
The sync-ledger fence check still reads the serving sync fleet: incompatible
fence modes require a coordinated rollout, not a partial deploy.

Selected services get the usual rendered-state validation, live drift check,
ready revision checks, exact release-vector verification and revision-specific
traffic promotion. The backend audio/API probes run when `backend` is selected.
The manual workflow artifact `backend-deployment-evidence-<run-id>-<attempt>`
contains candidate/serving release vectors and the pre-promotion traffic
snapshot, limited to the selection.
A failed traffic shift, serving-vector verification or serving smoke restores
only the snapshot's services. Unselected services need not run the same SHA.

`service_images` remains an optional image override, separate from service
selection. Every override must name a selected service and a same-SHA role
image digest; an override never implicitly selects a service. Blank means the
selected services use the newly built `backend:<sha7>` image, **not** their
previous live images. See [role image cutover](role-image-cutover.md).

## Per-service rollback (release role only)

Before dispatch, record each selected service's **positive-traffic revisions and
percentages from `status.traffic`**, plus its tags. Never infer the serving release
from `latestCreatedRevisionName` or the service template. Keep this record with
the release evidence. The workflow also captures restorable routing metadata
immediately before promotion; download its artifact for rollback after the run.

For a single prior revision, the release role can restore just that service:

```bash
gcloud run services update-traffic backend-integration \
  --project=<project> --region=us-central1 \
  --to-revisions=<previous-serving-revision>=100 --quiet
gcloud run services describe backend-integration \
  --project=<project> --region=us-central1 --format='json(status.traffic)'
```

For a prior traffic split, pass every captured revision/percentage pair instead
of `=100`. Or use the workflow-owned traffic snapshot restorer to restore all
and only the services in that snapshot:

```bash
python3 backend/scripts/cloud_run_traffic_snapshot.py restore \
  --snapshot backend-cloud-run-pre-promotion-traffic-snapshot.json \
  --evidence-path backend-cloud-run-traffic-restore.json
```

Traffic rollback routes to the prior revision's image and env. It does not undo
service-level settings or IAM changes, nor remove candidate revisions. Reconcile
those separately through the reviewed release controls if needed. Reverting the
code change removes the selector feature; omitting `services` deploys the full
stack and is **not** a per-service rollback.

## Fallback: build-only plus an image-only move (release role only)

Use this only when the workflow cannot express the required release, with the
release owner's approval and serialized under the same deploy lock. First run
`gcp_backend.yml` from main with `mode=build-only`, the exact admitted
`release_sha`, requester and environment, leaving `services` and `service_images`
blank. Build-only retains eligibility and production approval and publishes
immutable images; it changes no service or traffic. Use the run's verified
digest and source identity, never `latest`. Role images must match the target
service's `OMI_ROLE` (see the role image runbook).

Capture that service's serving revision/traffic and exported configuration.
Then stage the image change without changing its env or routing live requests:

```bash
gcloud run services update backend-integration \
  --project=<project> --region=us-central1 \
  --container=backend-integration \
  --image=gcr.io/<project>/backend@sha256:<verified-build-only-digest> \
  --revision-suffix=<unique-release-suffix> --no-traffic --quiet
```

The release role must verify the exact new revision is Ready, its image digest
and source identity match the build evidence, and its env/secret bindings,
sidecars and service identity match the captured configuration. An inherited
`OMI_BACKEND_RELEASE_SHA` or `commit-sha` marker may describe the old revision:
record that discrepancy explicitly; do not claim the normal workflow's full
release-vector proof. Apply the normal drift checks and appropriate acceptance
probe before promoting with `--to-revisions=<exact-new-revision>=100`. Verify
`status.traffic` and the serving revision's identity afterward. Roll back using
the per-service command above. This fallback requires operator evidence and
does not bypass approval, admission or the release lock.
