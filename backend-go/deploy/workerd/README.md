# Dev workerd deployment

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
