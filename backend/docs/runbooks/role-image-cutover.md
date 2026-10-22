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

1. `llm-gateway` and `pusher`. The stack path above covers the gateway only in
   development (`deploy_gateway=true`); production gateway ships through
   `gcp_llm_gateway.yml` and pusher through `gcp_backend_pusher.yml`, which
   still build their own images: each needs a role-digest input (pusher's
   `pusher_image_digest` qualification flow must accept `backend-pusher`)
   before its production cutover.
2. `messaging-maintenance-job`: switch the admitted image in
   `backend/deploy/messaging/maintenance-job.json` / `messaging_operations.py`
   to the `backend-workers` digest.
3. `backend-listen`: `service_images=backend-listen=…` with `deploy_targets=all`
   (development), then the production path.
4. The Cloud Run four in one train (`backend` → `backend-api`, the other three →
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
