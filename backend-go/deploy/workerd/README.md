# Workerd deployment

## Development

The chart follows the backend GKE Helm pattern with a digest-pinned image, pod probes
and Managed Prometheus `PodMonitoring`. It creates the Deployment only in
`dev-omi-backend`. Run the following steps from the repository root against an explicitly
selected dev GKE context.

1. Provision a dedicated Postgres 16 queue database in dev Cloud SQL. The GKE cluster must
   have VPC reachability to the instance's private IP. Use a direct TLS Postgres URL, following
   the private-IP route of `backend/database/jobstore/connection.py`. This worker uses database
   credentials from a dedicated Secret, whereas the Python staging jobstore mints IAM tokens
   per connection. Provision a database/schema owner for migrations and a runtime login with
   schema usage, queue DML, sequence usage, and function execution. Give the runtime role
   `SELECT` on `queue_schema` and set default privileges for future migrations.
2. In `dev-omi-backend`, provision `dev-omi-workerd-migrator` with its `DATABASE_URL` and
   `dev-omi-workerd-runtime` with its own `DATABASE_URL` and dev-only `ENCRYPTION_SECRET`.
   Use the dev secret provisioning process. The chart pins `FIRESTORE_PROJECT` to
   `based-hardware-dev` and the initial worker requires no Google API credentials.
3. The normal image path is the `Build and publish workerd development image` job in
   `.github/workflows/gcp_backend_auto_dev.yml`. When a successful Release Eligibility run for
   a main SHA includes `backend-go/` changes, source admission resolves the newest eligible
   main SHA and the job builds from that exact admitted SHA. It pushes
   `gcr.io/based-hardware-dev/workerd:<short-sha>` with the development Workload Identity, and
   prints the immutable digest in the job summary. A workerd-only change runs GitHub
   source admission and the dev registry publish. The serving Firestore check and backend
   deploy require their own backend scope. Use the reported digest as `WORKERD_DIGEST`.

   Until the workflow job is available, the following local build and push is an interim path
   only: use the authorized dev registry identity to run
   `make -C backend-go image IMAGE=gcr.io/based-hardware-dev/workerd:<short-sha>`, then
   `docker push` and resolve the digest. Set `DEV_GKE_CONTEXT` to the verified dev Kubernetes
   context and confirm Managed Prometheus is installed.
4. Create the one-shot migration Job, wait for completion, then install the Deployment
   with the same image digest.

   ```sh
   helm template dev-omi-workerd backend-go/deploy/workerd \
     --namespace dev-omi-backend --set-string image.digest="$WORKERD_DIGEST" \
     --set migration.enabled=true --show-only templates/migration.yaml |
     kubectl --context "$DEV_GKE_CONTEXT" -n dev-omi-backend create -f -
   kubectl --context "$DEV_GKE_CONTEXT" -n dev-omi-backend wait \
     --for=condition=complete job/dev-omi-workerd-migrate --timeout=2m
   helm --kube-context "$DEV_GKE_CONTEXT" --namespace dev-omi-backend upgrade --install \
     dev-omi-workerd backend-go/deploy/workerd --set-string image.digest="$WORKERD_DIGEST"
   kubectl --context "$DEV_GKE_CONTEXT" -n dev-omi-backend rollout status \
     deployment/dev-omi-workerd --timeout=3m
   ```

   If migration fails, inspect its dev Job status before retrying. Delete a completed Job
   before manually rerunning it if its TTL has yet to expire.
5. Port-forward the dev Deployment's health and metrics ports to localhost. Verify
   `/health` and `/ready` on 8080, and `/metrics` on 9090. Check that both stranded gauges
   are scraped. With an empty smoke database, both are zero.

## Production release

Release owns the install and activation. First run the dev procedure above with this chart and
record the image digest, rollout status, `/ready` response and both Managed Prometheus stranded
gauges. Leave optional maintenance and serving settings unset. Python owns ordinary finalization.

### Publish and prepare

- After the lead authorizes the workflow change at the reviewed PR head and it merges,
  dispatch `.github/workflows/gcp_backend.yml` from main with
  `mode=workerd-image-only`, `environment=prod`, `requested_by`, and the exact eligible
  main `release_sha`. Keep the other inputs at their defaults. The normal admission and
  protected prod Environment apply. Record the source and `gcr.io/based-hardware/workerd@sha256:…`
  from the Actions summary. Use its digest as `WORKERD_DIGEST`.
- Confirm the production GKE context and `prod-omi-backend` namespace. On the existing
  `prod-jobs` Postgres 16 instance, David provisions a dedicated queue database and
  migrator and runtime roles with the privileges described above. From GKE, the database
  must be reachable over its private IP using TLS. David supplies `prod-omi-workerd-migrator`
  with `DATABASE_URL`, and `prod-omi-workerd-runtime` with the runtime role's `DATABASE_URL` and
  `ENCRYPTION_SECRET`. The production overlay selects the prod registry and
  `FIRESTORE_PROJECT=based-hardware`.

### Migrate, install and verify

Run from the repository root with `PROD_GKE_CONTEXT` set to the verified prod context.
Render and run only the migration Job before installing or updating the Deployment.

```sh
set -eu
chart=backend-go/deploy/workerd
release=prod-omi-workerd
namespace=prod-omi-backend
helm template "$release" "$chart" -f "$chart/values-prod.yaml" \
  --namespace "$namespace" --set-string image.digest="$WORKERD_DIGEST" \
  --set migration.enabled=true --show-only templates/migration.yaml |
  kubectl --context "$PROD_GKE_CONTEXT" -n "$namespace" create -f -
kubectl --context "$PROD_GKE_CONTEXT" -n "$namespace" wait \
  --for=condition=complete "job/$release-migrate" --timeout=2m
helm upgrade --install "$release" "$chart" -f "$chart/values-prod.yaml" \
  --kube-context "$PROD_GKE_CONTEXT" --namespace "$namespace" \
  --set-string image.digest="$WORKERD_DIGEST" --atomic --timeout 5m
kubectl --context "$PROD_GKE_CONTEXT" -n "$namespace" rollout status \
  "deployment/$release" --timeout=3m
```

On migration failure, inspect the Job logs and reconcile migration state before retrying.
Kubernetes garbage-collects the Job after its 600-second TTL. Delete a completed Job
before rerunning the migration if the TTL has yet to expire. Verify both replicas run
the pinned digest. Port-forward the Deployment on 8080 and 9090 and check `/health`, `/ready`
and `/metrics`. Verify that the `PodMonitoring` targets are healthy and both
`omi_queue_stranded_jobs` and `omi_queue_stranded_oldest_due_seconds` are scraped.

### Enable and verify private intake when Release has approval

The chart follows the prod diarizer's regional internal Gateway and HTTPRoute pattern.
It uses a dedicated HTTPS listener because the prod ML Gateway listens on HTTP. Reserve
a regional internal IP for the Gateway in the GKE VPC, configure private DNS for its exact
hostname, and provision a same-namespace Kubernetes TLS Secret with a matching certificate
trusted by the Cloud Run producer. Verify private VPC egress and regional reachability from
that producer. Provision a dedicated GKE workload identity with Firestore transaction access
to `based-hardware`, and bind the named Kubernetes service account `prod-omi-workerd` to it.
[GKE Gateway capabilities](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/gatewayclass-capabilities#httproute)

Apply an additional Release values file with these settings, using the actual provisioned
names. Keep the pinned digest and production values from the install above.

| Helm value | Release input |
| --- | --- |
| `intake.enabled` | `true` |
| `intake.hostname` | Exact private DNS hostname |
| `intake.addressName` | Reserved regional private address resource name |
| `intake.tlsSecretName` | Kubernetes TLS Secret name |
| `intake.audience` | The exact token audience, use the private HTTPS origin |
| `intake.caller` | Full runtime service-account email of the Cloud Run notifier |
| `intake.firestoreServiceAccount` | Dedicated GKE workload's Google service-account email |

Verify `Gateway` is Programmed, the `HTTPRoute` reports Accepted and ResolvedRefs for the
HTTPS listener, and the Service backend is healthy on `/ready`. From the real Cloud Run
producer, verify private DNS and TLS, then check that an unsigned POST yields 403 and a
GET to the exact path yields 405. For each signed probe, use a token minted for the
configured audience by the allowed runtime service account and a receipt from an
already-bound fixture in that worker's Firestore project. Release must approve the
fixture for that environment. It must use a dedicated test account and synthetic data,
with both the conversation's `episode_id` and its `episode_links` binding already
populated. Never use customer data. Expect 200 with no writes on replay. Verify that
requests to a wrong host or path are unrouted. After Release approval, set the producer's `SYNC_EPISODE_INTAKE_ORIGIN` to the
private HTTPS origin and `WORKER_EPISODE_INTAKE_AUDIENCE` to the value used by workerd. Run
the eligible Python sync intake flow and verify 200, 204 or an expected stale 409.
Record responses and metrics without logging tokens, receipts or tenant IDs.

### Roll back

Clear the Python notifier's origin and audience, then apply the baseline chart with
`intake.enabled=false` to withdraw the route and remove server intake configuration.
If the worker image also needs reverting, use the last known healthy digest with the
baseline chart and repeat the rollout and metrics checks. Verify that digest accepts the
current migration checksums before switching. If there is no compatible prior image,
leave intake off and fix forward. Preserve the queue database and its rows.

### First ordinary finalization cohort

Parallel full finalization can duplicate document writes, integrations and paid calls.
Go queue guards and keyed model operations deduplicate Go retries. Python has its own
finalization path. This release keeps Python as sole finalization owner. The intake route
only repairs an existing binding selected by Python.

A future first cohort is one explicitly allowlisted owner on the eligible ordinary sync
producer. It requires all serving ports, a shared per-conversation ownership fence across
producers and consumers, and a bounded drain plus fenced handback. To revert that cohort,
close Go admission, drain or reconcile in-flight work and paid effects, then atomically
return outstanding conversations to Python under the same fence. Python resumes those
conversations only after handback. Keep the remainder of traffic on Python throughout.

## Chart render tests

With Helm on PATH, run `bash backend-go/deploy/workerd/test-render.sh` from the repository root.
