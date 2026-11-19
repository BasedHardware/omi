# 2026-11-19: backend-projection-pump becomes a deployable, dark, fifth Cloud Run target

Tracking: SCA-3120. This change delivers step (ii) of
[`2026-11-08-projection-pump-deploy-bundle.md`](2026-11-08-projection-pump-deploy-bundle.md), the dedicated
service deploy. That bundle noted that the backend workflow had no `backend-projection-pump` target. This
change adds the target. It does not run a deploy, and it does not enable the pump.

## What changed

- **Selection.** `gcp_backend.yml` accepts `cloud_run_service=backend-projection-pump`.
  - It accepts it only for `mode=deploy`, `deploy_targets=cloud-run-only` and `environment=prod`.
  - The break-glass lock and the eligibility skip must both be off, and `service_images` must be empty.
  - `all` still selects exactly `backend`, `backend-sync`, `backend-sync-backfill` and `backend-integration`
    (`scripts/cloud_run_scope.py`: `SERVICES` is unchanged, and the new `PROJECTION_PUMP` is listed in
    `SELECTABLE` only).
  - auto-dev and staging never deploy the pump. `compose_staging` excludes it explicitly through
    `STAGING_EXCLUDED_SERVICES`.
- **Deploy path.** The new composite `.github/actions/deploy-projection-pump` runs from the new job
  `deploy-projection-pump`.
  - The job runs under the same workflow-level prod-train concurrency group as the stack deploy, with the
    same admission, Firestore readiness and break-glass jobs.
  - The stack `deploy` job never runs for the pump. `deploy-backend-stack` is byte-identical, so the four
    services keep their exact step list.
  - The composite reuses the existing scripts: the image resolver, the renderer (`runtime-env`), the
    pre- and post-deploy validators, `deploy-cloudrun`, the GMP sidecar attach, wait-ready, the release
    vector, the traffic snapshot and restore, and the custody artifact.
  - It never builds an image. It requires `gcr.io/based-hardware/backend:<short sha>`, which a train or a
    build-only run has already published for the admitted SHA.
- **Service shape.** 2 vCPU, 4Gi, `--no-cpu-throttling`, min = max = 4, timeout 3600s, `--ingress=internal`,
  `--no-allow-unauthenticated` and no invoker binding. It uses the same runtime service account, VPC and
  network flags as `backend-integration`.
  - The new `scripts/verify_projection_pump_shape.py` reads back the shape before any traffic moves:
    ingress, the public-member IAM check, fixed 4/4, always-allocated CPU, timeout, and the dark env.
- **Env.** The manifest declares `backend-projection-pump: derive_from: backend-integration` in
  `deploy/runtime_env/prod.overlay.yaml`. `compose_runtime_env.py` expands it after the base and overlay
  merge, so the pump tracks every later change to integration's prod env.
  - Overrides: `BATCH_PIPELINE_SERVING_ENABLED=false`, `BATCH_PIPELINE_PROJECTION_PUMP_ENABLED=false`,
    `BATCH_PIPELINE_PUMP_SWEEP_PAGES=1`, `BATCH_PIPELINE_PUMP_TICK_SECONDS=2`,
    `BATCH_PIPELINE_MAX_OWNER_DRAINS=8`, `FIRESTORE_READ_LEDGER_SERVICE=backend-projection-pump` and
    `BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED=false`.
  - Handler and task URLs still point at the existing services.
- **Metrics.** The new profile `deploy/cloud_run_gmp_projection_pump.yaml` is the sync keep-list plus
  `omi_batch_projection_pump_last_(success|tick)_seconds`. The follow-up outcomes counter already matches
  `batch_pipeline_.*`. The profile adds `targetLabels.metadata: [service, revision]`, so (iv) can select
  `revision_name`. The shared profiles are unchanged.
- **Checks.** The staging-mirror check skips the services the composer excludes from staging. The
  cross-service reader-split check treats the pump as role-local (`READER_SPLIT_ROLE_LOCAL`), so the batch
  worker is still compared against the serving fleet and not against the pump's own tick and recovery
  overrides. Pinned tests that list per-service values now include the derived pump in prod.
- **Alert.** This change adds no stale-tick alert. That alert lands at bundle step (iv), after the dark
  deploy, and is retargeted to the receiving revision.

## Deviations from the brief

- **`SONIOX_API_KEY` stays bound.** `main.py` startup runs `validate_streaming_stt_env()`. Under integration's
  prod env (`STT_GPU_FLEET_OFF=true`, default streaming models that include soniox), that check raises when the
  key is empty. Removing the binding would crash the pump at start.
  - No other inherited binding was proven unused, so all integration secrets are kept.
- **No `ops/prod.yaml` entry yet.** `ops_train.plan_service` blocks every config train on an unreadable
  service. An entry made before the service exists would stop all trains. For now, the deploy step's literals
  own min = max = 4.
  - Add `cloud_run.backend-projection-pump` to `ops/prod.yaml` in the first config change after the dark
    deploy has been read back. From then on, the ops file owns the bounds.

## Ramp plan

| Step | Who expands | Clean metric to hold | Rollback |
| --- | --- | --- | --- |
| 1. Dark deploy: `gh workflow run gcp_backend.yml -f mode=deploy -f environment=prod -f deploy_targets=cloud-run-only -f cloud_run_service=backend-projection-pump -f requested_by=<owner>` | Release owner executes; SCA-3120 owner reads back | Read back from the live service: ingress `internal`, no `allUsers`/`allAuthenticatedUsers` binding, env flags false, ledger name `backend-projection-pump`, and four instances scraped with `revision_name`. Also hold integration's `omi_batch_pipeline_projection_followup_outcomes_total{outcome="completed"}` per hour and the Firestore read rate at the pre-deploy baseline. | `gcloud run services delete backend-projection-pump` (nothing routes to it) |
| 2. Enable the pump alongside the serving sweeps: set `BATCH_PIPELINE_PROJECTION_PUMP_ENABLED=true` in the manifest and redeploy through this target | Release owner executes; lead2 reviews custody evidence first | Fresh `omi_batch_projection_pump_last_success_seconds` from four instances on the receiving revision. Follow-up `completed` per hour at or above baseline. Owner-drain at or above 70% of baseline. Firestore reads within +50% of baseline. Bundle (iv) alert installed and read back. | Pump flag back to false (manifest plus redeploy), or restore the prior revision's traffic |
| 3. Size N on follow-up `completed` per hour against the pre-change baseline | SCA-3120 owner proposes; release owner applies | As step 2, plus executor saturation and `claim_busy` share no worse than baseline | Revert N |
| 4. Switch the serving sweep off: `BATCH_PIPELINE_SERVING_PROJECTION_SWEEP=off` on `backend-integration` through the config train | Release owner (go-ahead on the release issue); lead2 reviews custody | Follow-up `completed` per hour sustained at or above baseline with the pump alone. No rise in `attempts_exhausted` or pending owners. | Serving sweep back on first |
| 5. Right-size CPU, memory and N | SCA-3120 owner reads back | As step 3 | Revert the size change |

Rollback order at any step: serving sweep back on first, then the pump flag off, then delete the service.

## Hazards

- **Leader leases on startup.** `main.py` startup tasks run unconditionally, and they are leader-leased.
  Four pump instances join every lease election, for example `upload_coalescing_scan` once the pump flag runs
  `drain_upload_holds`. In the dark deploy, verify the lease-contention counters and that lease holders stay on
  their current services.
- **Flag flips do not survive a train.** A runtime flip (such as bundle (iii-b)'s `gcloud run services update
  --update-env-vars`) lasts only until the next pump deploy re-renders the manifest value. Put every flip in
  `prod.overlay.yaml`.
- **Headroom gate.** The headroom gate reads a fixed-size service as N of N, which is always saturated. Exclude
  the pump from the headroom gate, or read it per instance.
- **Firestore reads.** Reads rise while the pump and the serving sweeps both run (steps 2 and 3). Keep the
  window short, hold the +50% read alarm, and read the pump's spend from its own ledger service name.
- **First create.** gcloud cannot create a service with `--no-traffic`, so the first deploy creates the base
  revision serving, then pins traffic to it by name before attaching the sidecar. The service is internal and
  dark, so this causes no exposure, but this path has not been run live.

## Review follow-ups that are not in this change

- **Read-ledger completeness (before step 2).** `backend/scripts/firestore_read_reconcile.py`
  requires snapshots only from the four shipped services, so a silent pump ledger would still
  read as complete. Adding the pump to `SHIPPED_SERVICES` before the service exists would make
  every reconcile incomplete, so it lands as its own change after the dark deploy is read back
  and before the pump flag is enabled. Owner: SCA-3120.
- **Inherited invoker grants.** The pre-traffic check reads the service's own IAM policy and
  refuses any `roles/run.invoker` member there. It does not read project or folder policy: a
  principal granted `roles/run.invoker` at the project can invoke every Cloud Run service in
  it, this one included, and that cannot be narrowed per service. The boundary this service
  relies on is internal ingress plus no service-level invoker; the routes it mounts keep their
  own authentication.
