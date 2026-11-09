# Role-image cutover (plan B B2/B3)

Plan B splits the fat `backend` image into role images built from one SHA:
`backend/Dockerfile.roles` targets `api`, `workers`, `realtime`, `gateway` and
`pusher`, plus the Rust `listen-edge` (`backend/edge/Dockerfile`). The
role → image → service map is `backend/runtime_images.json` (`roles`,
`services`, `native_images`). B2 only builds, probes and publishes the role
images. Nothing deploys them until a deploy opts a service in.

## What runs where

| Path | When | What it does | Pushes? |
|---|---|---|---|
| `.github/workflows/role_images.yml` | PRs that change an image input (Dockerfile.roles, locks, registry, contract scripts, `backend/edge/**`); every backend merge to main | Builds every role image on the public `python:3.11-slim` base, runs each role's offline dependency probe (`runtime_image_contracts.py smoke --target`), the listen-edge health/identity/drain probe, and records size and cold-start import time in the job summary | No |
| `gcp_backend.yml` `mode=build-only`, job `build-role-images` | Manual train dispatch from main, per environment | Same build and probe on the private base, at the admitted `release_sha`, stamped `OMI_RELEASE_SHA` and labelled `org.opencontainers.image.revision`; pushes `gcr.io/<project>/<image>:<sha7>` (never re-pushes a tag of another SHA) and prints the digests plus a ready `service_images` value. Also measures the fat `backend` image as a baseline | Yes, to the environment's registry |
| `gcp_backend.yml` `mode=deploy` with `service_images` | Manual, per environment | Moves the named services onto their role images by digest | n/a |

## The opt-in flag: `service_images`

`service_images` is a `gcp_backend.yml` dispatch input (and a
`deploy-backend-stack` input). **Blank, the default, deploys exactly what ships
today**: every Cloud Run service and listen runs `gcr.io/<project>/backend:<sha7>`,
the gateway `llm-gateway:<sha7>`. Merging B2 changed no deploy.

To opt in, pass space- or comma-separated `service=<ref>` pairs, using the
digests the build-only run of the **same** `release_sha` printed:

```
backend=gcr.io/based-hardware-dev/backend-api@sha256:<64 hex>
backend-sync=gcr.io/based-hardware-dev/backend-workers@sha256:<64 hex>
backend-sync-backfill=gcr.io/based-hardware-dev/backend-workers@sha256:<64 hex>
backend-integration=gcr.io/based-hardware-dev/backend-workers@sha256:<64 hex>
backend-listen=gcr.io/based-hardware-dev/backend-realtime@sha256:<64 hex>   # needs deploy_targets=all
llm-gateway=gcr.io/based-hardware-dev/backend-gateway@sha256:<64 hex>       # needs deploy_gateway=true (development)
```

`backend/scripts/resolve_service_images.py` fails the deploy before any
mutation unless each ref is a digest in this project's registry, of the role
image the registry maps that service to, labelled with the admitted SHA and
carrying that role's `OMI_ROLE`. The release-vector verifier then expects each
moved service at its digest (`--service-image`) and every other service at the
fat image, and records the per-service refs in its evidence.

Rollback: redeploy with `service_images` blank (or omit the service). The fat
image of the same SHA is still built and pushed by every deploy.

## B3 cutover order (lead-owned deploys)

Every step takes a digest that the **build-only** run of the same admitted
SHA printed (`gcp_backend.yml` `mode=build-only`: job summary and the
`role-images-<environment>` artifact). The standalone deploys admit a bare
digest through `backend/scripts/admit_role_image.py`: the repository is not
an input but derived from the registry (`services.<name>.image`), and the
image must be labelled `org.opencontainers.image.revision=<deployed SHA>` and
carry that role's `OMI_ROLE`, or the run fails before any mutation. Blank
inputs are the default everywhere and deploy exactly what ships today.

1. `llm-gateway` through `gcp_llm_gateway.yml` (production; development may
   also use the stack path, `service_images=llm-gateway=…` with
   `deploy_gateway=true`):

   ```
   gh workflow run gcp_llm_gateway.yml --ref main \
     -f environment=<development|prod> -f branch=main -f release_sha=<sha> \
     -f gateway_image_digest=sha256:<64 hex of backend-gateway at that sha>
   ```

   With a digest the run skips its own `llm-gateway:<sha7>` build, deploys
   `gcr.io/<project>/backend-gateway@<digest>` through `deploy-llm-gateway.sh`
   (`image.repository` + `image.digest`), proves the rolled-out Deployment
   template runs that exact reference, and runs the Cloud Run VPC probe and the
   smoke pod from the same image.

2. `pusher` through `gcp_backend_pusher.yml`:
   - Development: `-f environment=development
     -f pusher_role_image_digest=sha256:<64 hex of backend-pusher>` skips the
     fat build and deploys `gcr.io/based-hardware-dev/backend-pusher@<digest>`
     through the unchanged live-capacity gate, Helm release and receipts.
     Production rejects this input.
   - Production still ships only a development-qualified digest
     (`pusher_image_digest` + `pusher_dev_qualification_run_id`). The
     qualification flow admits evidence that names either
     `gcr.io/based-hardware-dev/pusher` or
     `gcr.io/based-hardware-dev/backend-pusher`
     (`verify_pusher_promotion_evidence.py --expected-repository` takes the
     comma-separated pair); the promotion keeps the repository name, so a
     role-image pusher lands as `gcr.io/based-hardware/backend-pusher@<digest>`
     and the final receipt is checked against that.
   - **Still needed before the production pusher cutover:** qualification
     evidence is produced only by `gcp_backend_pusher_auto_deploy.yml`, which
     builds the fat `pusher` image. That workflow has to deploy `backend-pusher`
     (a `.github` change for David to name), then one green run on the cutover
     SHA supplies the digest and run ID. Editing either pusher workflow or the
     verifier changes the promotion contract fingerprint, so qualification runs
     older than the change stop promoting; use the first green run after it.

3. `messaging-maintenance-job`: switch the admitted image to the
   `backend-workers` digest (prod registry, `gcr.io/based-hardware`):

   First admit the digest with the same tool the standalone deploys use — it
   derives the repository from `runtime_images.json`, proves the image is
   labelled with the release SHA you are admitting and carries the workers
   `OMI_ROLE`, so a digest from another commit or a misbuilt image fails before
   the job is touched (needs registry read access, e.g. `gcloud auth login` or
   an ADC identity with `storage.objects.list` on the GCR bucket):

   ```
   python3 backend/scripts/admit_role_image.py \
     --service messaging-maintenance \
     --digest sha256:<64 hex> \
     --project based-hardware \
     --admitted-sha <the release SHA this digest was built from>
   ```

   Then reconcile the job:

   ```
   python3 backend/scripts/messaging_operations.py job --check --image gcr.io/based-hardware/backend-workers@sha256:<64 hex>
   python3 backend/scripts/messaging_operations.py job --validate --image gcr.io/based-hardware/backend-workers@sha256:<64 hex>
   python3 backend/scripts/messaging_operations.py job --apply --image gcr.io/based-hardware/backend-workers@sha256:<64 hex>
   ```

   `desired_job` still admits exactly `gcr.io/based-hardware/backend@sha256:…`
   (today) or `gcr.io/based-hardware/backend-workers@sha256:…`; any other
   repository, registry or tag fails before gcloud authentication. The job's
   entrypoint `utils.messaging.maintenance` is one of the `backend-workers`
   image's probed entrypoints.

4. `backend-listen`: `service_images=backend-listen=…` with `deploy_targets=all`
   (development), then the production path.

5. The Cloud Run four in one train (`backend` → `backend-api`, the other three →
   `backend-workers`; `OMI_ROLE` stays unread until B8).

After each cutover, delete the replaced image entry, its `outside_role_split`
reason and the old Dockerfile: `pusher/Dockerfile` first, the fat `backend`
entry last (plan B §9f.5).

## Logging

All five role entrypoints (`main`, `utils.messaging.maintenance`,
`llm_gateway.main`, `pusher.main`) call `omi_logging.configure_logging(...,
default_format='text')`, so the role images are under the logging guard
(`scripts/check_logging_entrypoints.py`) and keep today's text logs and
`textPayload` filters. Switching a service to JSON is a separate, per-service
`OMI_LOG_FORMAT=json` step after its consumer admission
(`structured-logging-rollout.md`). listen-edge logs JSON through
`tracing-subscriber` and is outside the Python guard (`native_images`).
