# GCP development foundation

This directory targets only `based-hardware-dev` in `us-central1`. ADR-011 assigns this foundation to OpenTofu and the complete Cloud Run service, job, revision, scaling, secret-version bindings and traffic specification to the release workflow. There are no Cloud Run resources here. Do not reuse this state for production.

On 2026-09-07, the separate migration identity applied verified migration 53 from commit `9050eddcb5` to `omi-platform-dev-pg18` through the existing authenticated Cloud SQL proxy. The checksummed runner verified 52 existing migration receipts, applied only 53, and read back exactly 53 receipts. No account activation, application grant or entitlement records were synthesized. Before application, the local PostgreSQL 18.4 gate passed 28 tests and 11,169 assertions, restored 53 migrations and 120 tables, and passed the pinned Bun and Node adapter qualification. The private execution log is `~/.local/share/omi-v5-dev/operator/migrations-53.log`.

The Linux amd64 production image built from `9050eddc` is locally tagged `omi-v5-portable:9050eddc`; its image manifest is `sha256:d7508bce0b9a72736abbcd3547f18eb526ecb99db9586ef13f72e0d0f0d66236`. The bundled entry imported successfully, retained the request deadlines and rejected missing configuration. This image has not been deployed to Cloud Run, and initialized `/health` or `/ready` was not verified: the local operator did not have the complete runtime secret configuration. The local image reference is evidence of the build, not an Artifact Registry release reference or permission to bypass IAM.

The subsequent `b6e79abc2c` head passed GitHub Actions run `34067033002`, including backend PostgreSQL integration, runtime parity and Apple checks. Deployment was skipped; CI success does not change the deployment or authenticated health limitations above.

The foundation creates one zonal Enterprise PostgreSQL 18 instance (`db-custom-1-3840`, 10 GiB SSD with growth capped at 100 GiB), database `omi_platform`, a dedicated runtime service account, and three empty Secret Manager containers. Daily backups, seven-day point-in-time recovery, API deletion protection and OpenTofu destruction guards are enabled. This is a small development instance without regional high availability. Maintenance can interrupt it. PostgreSQL minor versions are managed by Cloud SQL; the application readiness check must verify the released PostgreSQL version before traffic admission.

Cloud SQL has a public address but no authorized networks, requires encrypted connections and rejects direct connections through connector enforcement. Release the API with the Cloud SQL Auth Proxy/connector attachment and the emitted connection name. The planned runtime service-account grants provide Cloud SQL client access and accessor access only to these three secrets and the existing `jit-qa-gateway-token` container. Cloud SQL IAM authorization does not replace database authentication: the current adapter consumes a static PostgreSQL URL and does not implement IAM database-token refresh.

## Review and bootstrap

OpenTofu 1.12 or later and pinned Google provider 8.1.0 are required. The applying operator needs Cloud SQL and secret-container creation plus `iam.roles.create`, project `setIamPolicy`, and `secretmanager.secrets.setIamPolicy`; resource-creation permission alone cannot complete runtime identity bindings. Authentication comes from the existing operator session, never from checked-in credentials or a provider variable. Every gcloud invocation must name the development project because the operator's CLI default can be production.

```sh
export GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token --project=based-hardware-dev)"
tofu -chdir=backends/example-platform/deploy/gcp/dev/bootstrap init
tofu -chdir=backends/example-platform/deploy/gcp/dev/bootstrap plan -out=/tmp/omi-platform-dev-bootstrap.tfplan
tofu -chdir=backends/example-platform/deploy/gcp/dev/bootstrap show /tmp/omi-platform-dev-bootstrap.tfplan
```

Apply only the reviewed saved bootstrap plan. It creates the isolated versioned state bucket with uniform access, enforced public-access prevention and destruction protection. Bootstrap initially uses local state; preserve it until it has been migrated. No other workspace may share its state file.

For an existing environment, restore the GCS backend configuration below before initializing bootstrap; do not start another local state or attempt to recreate its bucket. After first approved bootstrap application, create the ignored `bootstrap/backend.tf` file with this content and migrate the bootstrap state into the separate prefix:

```hcl
terraform {
  backend "gcs" {
    bucket = "based-hardware-dev-omi-platform-tfstate"
    prefix = "omi-platform/dev/bootstrap"
  }
}
```

```sh
tofu -chdir=backends/example-platform/deploy/gcp/dev/bootstrap init -migrate-state
tofu -chdir=backends/example-platform/deploy/gcp/dev init
tofu -chdir=backends/example-platform/deploy/gcp/dev plan -out=/tmp/omi-platform-dev-foundation.tfplan
tofu -chdir=backends/example-platform/deploy/gcp/dev show /tmp/omi-platform-dev-foundation.tfplan
```

Review the saved foundation plan for only this project's intended additions; reject any deletion or replacement. Apply that exact reviewed plan, then record resource outputs and the immutable release manifest. Refresh-only plans are the drift check; never auto-apply drift. If an apply partially succeeds, keep the remote state and generate a fresh saved plan. Have an authorized operator apply the remaining grants; do not destroy successful resources or broaden the runtime identity to work around denied IAM administration. Do not grant the runtime service account access to either state prefix. Protect saved plans and state as operator-only artifacts even though this configuration contains no secret payloads. Unset `GOOGLE_OAUTH_ACCESS_TOKEN` when finished; refresh it from gcloud if it expires. Do not print it or store it in a plan argument.

## Secret and database preparation

The named release operator owns secret versions and database credentials. OpenTofu creates no secret versions, passwords, service-account keys, root passwords or database-login credentials. Before releasing:

- Create the least-privilege application database login using an authenticated Cloud SQL administration connection. Apply migrations through a separate migration identity; do not grant the runtime login database ownership or general DDL rights.
- Populate `omi-platform-dev-database-url` with the connector-compatible PostgreSQL URL consumed by `OMI_DATABASE_URL`. Verify the driver and connector's actual socket or loopback connection before release.
- Populate `omi-platform-dev-codec-key` and `omi-platform-dev-cursor-key` with independently generated stable 32-byte keys encoded as 64 lowercase hexadecimal characters. Bind them to `OMI_CODEC_KEY_HEX` and `OMI_CURSOR_KEY_HEX` using explicit immutable secret-version numbers.
- Bind `OMI_FIREBASE_PROJECT_ID=based-hardware-dev`, the registered `OMI_APPLICATION_ID`, the verified `OMI_DATABASE_GENERATION_DIGEST`, and an explicit validated IANA `OMI_ACCOUNT_TIMEZONE`. Registration and the released generation digest are authority inputs, not generated defaults.
- Bind the existing approved `OMI_LLM_GATEWAY_URL`, `OMI_LLM_GATEWAY_SERVICE_TOKEN` and `OMI_MEMORY_RENDER_LANE`. The existing `jit-qa-gateway-token` container was verified in the development project and the adapter consumes its bearer token directly; this module grants narrowly scoped accessor access without taking ownership of that container or any versions.

Firebase token verification uses public signing keys and checks revocation/disabled-user state through `verifyIdToken(token, true)`. The runtime identity receives a dedicated custom role containing only `firebaseauth.users.get` on the development Firebase project; it receives no Firebase administrator or project editor role. The [Identity Platform permission table](https://cloud.google.com/identity-platform/docs/access-control) assigns `firebaseauth.users.get` to the underlying `GetAccountInfo` call. No new WIF pool, deployer impersonation grant, public invoker policy, GKE cluster, Redis or object bucket is needed for this operator-reviewed development foundation. A future automated release identity needs an explicit reviewed WIF and invoker policy before automation is enabled.

## Connection admission

`connection-budget.json` is the single source for the development budget. The SQL `max_connections` flag reads that file. It reserves three concurrent revisions, two instances each, four connections per instance, four migration connections and eight operator connections: `3 * 2 * 4 + 4 + 8 = 36`, below the admission ceiling of 70. Job allocations are zero in this first slice; adding a job requires a declared pool maximum, including overlap with retried tasks.

These revision caps are not applied by OpenTofu. The release workflow must enforce the ADR-011 sum over every serving, candidate and rollback revision plus jobs and reserves before creating a revision. Verify actual `max_connections` and provider-reserved capacity on the provisioned instance; the provisional three-connection reserve is not a live measurement. Do not admit application traffic until the approved ceiling is below measured usable capacity and the manifest's aggregate allocation is within that ceiling. Release tooling must consume this file rather than copying its numbers. The foundation alone is not a connection-admission implementation or production-readiness proof.

## Validation

```sh
tofu -chdir=backends/example-platform/deploy/gcp/dev fmt -check -recursive
tofu -chdir=backends/example-platform/deploy/gcp/dev init -backend=false
tofu -chdir=backends/example-platform/deploy/gcp/dev validate
tofu -chdir=backends/example-platform/deploy/gcp/dev/bootstrap validate
```

Provider reference: [Google SQL database instance 8.1.0](https://github.com/hashicorp/terraform-provider-google/blob/v8.1.0/website/docs/r/sql_database_instance.html.markdown). Architecture authority: `/Users/undivisible/workspace/omi/platform-tracker/decisions/ADR-011-gcp-first-runtime-infrastructure-and-delivery.md`.

## Prepare a Cloud Run release

`release-candidate.ts` creates the complete Cloud Run service specification and a release record; it never deploys or changes IAM. It reads the current development service through an explicitly project-scoped gcloud list call. Observation failure is fatal, and initial mode refuses to replace an existing service. Unknown input fields are rejected so credential payloads cannot accidentally become manifest fields.

Supply an operator-reviewed JSON file with these required fields:

| Field | Required evidence or format |
| --- | --- |
| `mode` | `initial-dev` for an observed absent service, otherwise `blue-green` |
| `image` | Immutable `us-central1-docker.pkg.dev/based-hardware-dev/…@sha256:` image reference with a 64-character lowercase digest |
| `sourceCommit` | Exact 40-character source commit used to build that image |
| `applicationId` | Actual registered application identity |
| `databaseGeneration` | Actual released database-generation digest, 64 lowercase hexadecimal characters |
| `accountTimezone` | Explicit validated IANA timezone |
| `gatewayUrl` | Approved HTTPS gateway URL without credentials, query parameters or fragments |
| `renderLane` | Registered `omi:auto:` semantic lane |
| `transcriptionModel` | Explicit Deepgram model, such as `nova-3` |
| `secretVersions` | Numeric immutable version strings for exactly `OMI_DATABASE_URL`, `OMI_CODEC_KEY_HEX`, `OMI_CURSOR_KEY_HEX`, `OMI_LLM_GATEWAY_SERVICE_TOKEN`, `OMI_TRANSCRIPTION_API_KEY`; no payloads or `latest` aliases |
| `residentRevisions` | Every revision that can concurrently hold connections, including rollback and zero-traffic revisions, each with actual `name`, `maxInstances`, and `poolMax`; empty only for initial mode |

Revision capacity declarations must come from the current release inventory and observed revision configuration. The script checks their shape, ceiling, coverage of observed traffic, and aggregate budget; it cannot establish that an operator omitted no dormant revision. Reconcile all resident revisions before preparing the input.

```sh
bun backends/example-platform/deploy/gcp/dev/release-candidate.ts "$OMI_RELEASE_INPUT" "$OMI_RELEASE_DIRECTORY"
```

The output directory must not already contain `service.json` or `release.json`. Files are created with operator-only permissions. The service specification fixes the dedicated runtime service account, Cloud SQL socket attachment, four version-pinned secrets, two concurrent requests, two instances per revision, one CPU, 512 MiB memory, and an HTTP `/ready` startup probe. The process pool maximum is four; release admission reads the shared connection budget. The immutable revision name hashes configuration as well as image, so rotating a secret version produces a new revision even when the image is unchanged.

For the database URL secret, the PostgreSQL driver must resolve `/cloudsql/based-hardware-dev:us-central1:omi-platform-dev-pg18`; the manifest sets `OMI_DATABASE_SOCKET_DIRECTORY` and mounts that socket. The adapter passes this directory explicitly to Postgres.js, overriding the URL host while retaining URL credentials and database name. Validate the secret URL's driver behavior through the real connector before readiness acceptance. Do not place its value in the release input or logs.

Initial mode explicitly assigns 100% of the new service's traffic to its first revision. This is an isolated private development bootstrap, not a zero-traffic blue-green release. Invoker IAM checking remains enabled, no public invoker grant is created, and no client route is switched. Verify the service is inaccessible anonymously after deployment; existing project-level IAM could affect who can invoke it. Blue-green mode resolves observed `latestRevision` traffic to its concrete previous ready revision and adds the new revision under the `candidate` tag with zero percent, retaining optimistic concurrency through the observed resource version.

After IAM, schema, identity registration and actual database-release evidence are ready, review the generated files and deploy the exact complete specification:

```sh
gcloud run services replace "$OMI_RELEASE_DIRECTORY/service.json" --project=based-hardware-dev --region=us-central1
```

This command does not create or update invoker IAM. Re-read the service and revision configuration after deployment, verify the image digest, identity, secret-version references, pool/cap inventory, observed traffic and anonymous denial. Test `/ready` using an authorized Cloud Run caller, then run the authenticated memory contract against the initial service or the zero-traffic candidate tag. For a private service, Cloud Run's IAM token can use `X-Serverless-Authorization` while the application Firebase token remains in `Authorization`; do not log either token. A successful health check alone does not prove a Firebase-authorized memory read.

Promotion and rollback are separate reviewed release actions. Only after candidate acceptance, select the exact candidate revision for promotion through `gcloud run services update-traffic` with explicit development project and region. Record the prior revision and traffic before promotion, and rollback by restoring that exact revision without rebuilding. This preparation script never promotes, deletes a revision, creates a release receipt, or claims a runtime qualification result.

The regression runs with `bun test deploy/gcp/dev/release-candidate.test.ts` from the example-platform package and must remain in its deployed acceptance command. The Cloud Run [no-traffic option](https://cloud.google.com/sdk/gcloud/reference/run/deploy#--no-traffic) freezes existing latest traffic onto the previous concrete revision; the initial-mode semantics above are deliberately recorded separately.
