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
    ingress, the public-member IAM check, fixed 4/4, always-allocated CPU, timeout, and the env.
    It refuses `BATCH_PIPELINE_SERVING_ENABLED` other than `false` and `OMI_PROCESS_ROLE` other than
    `projection_pump` unconditionally. The pump flag and the ledger name must match the rendered manifest.
- **Env.** The manifest declares `backend-projection-pump: derive_from: backend-integration` in
  `deploy/runtime_env/prod.overlay.yaml`. `compose_runtime_env.py` expands it after the base and overlay
  merge, so the pump tracks every later change to integration's prod env.
  - Overrides: `OMI_PROCESS_ROLE=projection_pump` (see Startup isolation),
    `BATCH_PIPELINE_SERVING_ENABLED=false`, `BATCH_PIPELINE_PROJECTION_PUMP_ENABLED=false`,
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

## Startup isolation

Without a gate, `main.py` `startup_event` starts every reconciler, refresher and consumer on every process.
The pump is deployed only when someone selects it, so it can stay on an older SHA than the trains for any
length of time. An old-code pump instance could then win a deletion, purge or finalization lease.

- **Gate.** `config/process_role.py` reads `OMI_PROCESS_ROLE`, and `startup_event` resolves it first. The
  set of values is closed:
  - unset or `all`: today's full startup, in today's order, for every existing service;
  - `projection_pump`: set only on `backend-projection-pump` in `prod.overlay.yaml`;
  - any other value: startup fails with `ProcessRoleConfigError`.
- **Independence.** The role is separate from `OMI_ROLE`, which selects routers, and from the batch kill
  switches. Turning `BATCH_PIPELINE_PROJECTION_PUMP_ENABLED` off stops the pump loops, but it does not bring
  the reconcilers back.
- **Contradictory config fails closed.** Under the pump role, `BATCH_PIPELINE_SERVING_ENABLED=true` fails
  startup.
- **Defense in depth.** `_run_fsr_loop` returns `{}` under the pump role before it takes any lease. A later
  caller therefore cannot bring a reconciler back onto the pump.

What the pump keeps, in startup order:

| Kept | Why |
| --- | --- |
| `start_metrics_sidecar_server` | The GMP sidecar scrapes the pump's success and tick gauges from it |
| `refresh_stt_cap_cohort_forever` | The projector's assignment path consults the STT cap cohort (`projection.py` `cap_dispatch_enabled`); this is a read-only cache poller |
| `start_serving_from_env()` | Selects the pump loops (`projection_pump`, `drain_upload_holds`, and the outbox supervisor when its switch is on), or nothing while the pump flag is off |
| `validate_account_deletion_dispatch_configuration`, `validate_streaming_stt_env` | Kept so the pump's env and secret contract is unchanged in this change |
| `log_executor_health` | Executor saturation is one of the ramp metrics |
| `retry_settled_composes` | The projector enqueues episode transcript receipts into a process-local queue, and only this task drains it. Skipping it would strand them (10k cap, then drop) |

What the pump skips:

| Skipped | Why |
| --- | --- |
| `start_mutations` and the Pinecone shutdown-drain install | The projection path writes no Pinecone vectors |
| `start_adapters` (messaging) | The pump serves no webhooks and must not run a second `recover_pending` drainer |
| `live_stt_health.refresh_forever`, `batch_pressure.start_from_env` | Only live-STT paths read them |
| Held-content cohort refresh | Only the budget-choice HTTP route reads it |
| Soniox usage poller | It is vendor usage reporting that the projector does not use |
| Startup and periodic `_run_fsr_loop` reconcilers: pending deletion wipes, listen finalization jobs, stale processing and stale in-progress conversations, abandoned BYOK finalization, conversation batch purges | These are privacy and custody work. An old-SHA pump must never hold their lease |
| Durable queue-age publisher | Already opt-in per service, and it is leased through `_run_fsr_loop` |
| `proactive_message_dispatcher` | It forwards Pub/Sub to this process's WebSocket sessions, and the pump has none |

`shutdown_event` is unchanged. On the pump it skips the unset app state, drains an empty Pinecone registry,
stops a batch-pressure poller that never started, and has no lease token to release.
`tests/unit/test_process_role_startup.py` pins the exact task sets for the default role, the dark pump and the
active pump. It also covers unknown roles, serving on the pump, the lease bypass, shutdown and `OMI_ROLE`
independence.

Not isolated yet:

- **Import-time work** is unchanged on the pump: `validate_stripe_price_ids`, Firebase init and the rollout
  runtime binding.
- **The secret set** is unchanged. The pump still inherits integration's secrets, because both startup
  validators still run. Trimming them is a separate change.
- **Mounted routers** are unchanged. `OMI_ROLE` is unset, so every router is mounted. Internal ingress and no
  invoker are the boundary.

**Rollback.** Unset `OMI_PROCESS_ROLE` on the pump through the manifest and a pump deploy. That restores full
startup, including every reconciler election, so do not leave the service running in that state. Stop the
pump flag and delete the service instead.

**Owner check before the dark deploy.** The deletion, purge and finalization owners and lead2 are asked to
confirm that the four train services still cover each of these reconcilers: deletion wipes, listen
finalization, stale processing and stale in-progress conversations, BYOK abandonment, and batch purges. The
pump no longer competes for any of them.

## Ramp plan

| Step | Who expands | Clean metric to hold | Rollback |
| --- | --- | --- | --- |
| 1. Dark deploy through SCA-3318 using the dispatch and recovery procedure below | Release owner executes; SCA-3120 owner reads back | Read back the ready serving revision, source SHA and image digest, internal ingress, service IAM, dark batch flags, ledger identity, and four instances scraped with `revision_name`. Hold integration's follow-up completions per hour and Firestore read rate at the pre-deploy baseline. | Verified dark inverse for promotion failure. Release records the disposition for an incomplete first create. |
| 2. Enable the pump alongside the serving sweeps: set `BATCH_PIPELINE_PROJECTION_PUMP_ENABLED=true` in the manifest and redeploy through this target | Release owner executes; lead2 reviews custody evidence first | Fresh `omi_batch_projection_pump_last_success_seconds` from four instances on the receiving revision. Follow-up `completed` per hour at or above baseline. Owner-drain at or above 70% of baseline. Firestore reads within +50% of baseline. Bundle (iv) alert installed and read back. | Pump flag back to false (manifest plus redeploy), or restore the prior revision's traffic |
| 3. Size N on follow-up `completed` per hour against the pre-change baseline | SCA-3120 owner proposes; release owner applies | As step 2, plus executor saturation and `claim_busy` share no worse than baseline | Revert N |
| 4. Switch the serving sweep off: `BATCH_PIPELINE_SERVING_PROJECTION_SWEEP=off` on `backend-integration` through the config train | Release owner (go-ahead on the release issue); lead2 reviews custody | Follow-up `completed` per hour sustained at or above baseline with the pump alone. No rise in `attempts_exhausted` or pending owners. | Serving sweep back on first |
| 5. Right-size CPU, memory and N | SCA-3120 owner reads back | As step 3 | Revert the size change |

Rollback order at any step: serving sweep back on first, then the pump flag off, then delete the service.
Deleting the service also needs `backend-projection-pump` removed from the read reconcile's required
set first (`firestore_read_reconcile.py`), or every later day scores incomplete. A first create stays
dark by policy (the first-create gate refuses an activated manifest): recreate from a manifest with
the pump flag `false`, read back the dark base, then activate as step 2.

After step 2 the routed pump revision is the activated one. The pre-mutation inverse check
(`verify_projection_pump_inverse.py --disposition`) accepts a pinned routed revision whose
`BATCH_PIPELINE_PROJECTION_PUMP_ENABLED` is the literal `'true'`, and otherwise the dark values. A
base before its first pin and a new create must still be dark. The fastest pump rollback is a
traffic restore to the recorded dark revision; a flag-false redeploy is the second option.

## Dark dispatch and interrupted first-create recovery

Release records the full admitted runtime SHA and the full dispatch control SHA in SCA-3318.
Verify the published fat-image digest for the runtime SHA. Obtain independent review of the
exact control carrier on main, including the workflow, composite and the staged `.github`,
`backend/scripts` and `backend/deploy` controls it will use. Record those Git object IDs
with the review. Dispatch from main as below after the Release Eligibility, Firestore readiness,
production approval and shared prod-train gates. A change to main between review and dispatch
causes the pump job to stop. Check the run's control evidence against the receipt.

```sh
gh workflow run gcp_backend.yml --ref main \
  -f mode=deploy -f environment=prod -f deploy_targets=cloud-run-only \
  -f cloud_run_service=backend-projection-pump -f requested_by="$release_owner" \
  -f release_sha="$admitted_source" -f pump_control_sha="$reviewed_control"
```

For first create, Release records that the service is absent. Cloud Run initially sends traffic
to LATEST. The workflow checks the new Ready dark base before pinning it, verifies the pin,
and then attaches the zero-traffic sidecar. It reads the inverse again before promotion and
captures the rollback snapshot from that same verified traffic document.

If a run stops during first create, stop before any pin, redeploy or rerun. Release uses
`ro-prod` to inspect requested and serving traffic, the receiving revision and the service IAM
policy. Match the revision's Ready condition, admitted source stamp and fat-image digest
against the original release evidence. Verify the projection pump role, both false flags,
ledger identity, internal ingress, enabled IAM invoker check, no service invokers, and fixed
4/4 shape with always-allocated CPU, 2 vCPU, 4 GiB, concurrency 80 and a 3600-second timeout.

Release records the disposition on SCA-3318. If the evidence is incomplete or any check fails,
hold and obtain a separate Release-approved recovery action. If the evidence passes and
traffic still follows LATEST, Release may pin the verified revision under the production
mutation lock as authorized by the recorded disposition, then read back both traffic views.
A base already pinned at the time of interruption requires the same verification and disposition.

For an existing service, include
`-f pump_release_disposition="$comment_uuid $revision $inverse_source $inverse_image"` in the
new dispatch. The production approver verifies that the referenced Release comment authorizes
resuming with that revision and identity, using the actual inputs in the workflow's
pre-approval summary. Use `repository@sha256:digest` for the image.
Use the serving revision's own admitted source and digest from Release evidence, which may
predate the new candidate. The workflow binds the dispatch input to live data and stops before
mutation unless requested and serving traffic agree on exactly the Ready revision the disposition
names (dark, or the activated pump after step 2). Record the run ID and independent serving and
baseline readback in the Release order.

## Hazards

- **Leader leases on startup.** With `OMI_PROCESS_ROLE=projection_pump` the pump joins no FSR reconciler
  election (see Startup isolation). It still joins the batch leases its own loops take, for example
  `upload_coalescing_scan` once the pump flag runs `drain_upload_holds`. In the dark deploy, verify that
  `omi_fsr_leader_lease_total` shows no acquisitions from pump revisions and that lease holders stay on their
  current services.
- **Flag flips do not survive a train.** A runtime flip (such as bundle (iii-b)'s `gcloud run services update
  --update-env-vars`) lasts only until the next pump deploy re-renders the manifest value. Put every flip in
  `prod.overlay.yaml`.
- **Headroom gate.** The headroom gate reads a fixed-size service as N of N, which is always saturated. Exclude
  the pump from the headroom gate, or read it per instance.
- **Firestore reads.** Reads rise while the pump and the serving sweeps both run (steps 2 and 3). Keep the
  window short, hold the +50% read alarm, and read the pump's spend from its own ledger service name.

## Review follow-ups that are not in this change

- **Read-ledger completeness (before step 2).** `backend/scripts/firestore_read_reconcile.py`
  requires snapshots only from the four shipped services, so a silent pump ledger would still
  read as complete. Adding the pump to `SHIPPED_SERVICES` before the service exists would make
  every reconcile incomplete, so it lands as its own change after the dark deploy is read back
  and before the pump flag is enabled. Owner: SCA-3120. Done in the step-2 activation PR (#25966):
  the pump is in `SHIPPED_SERVICES` and `HOT_SERVICES`; the dark successor already emits snapshots.
- **Inherited invoker grants.** The pre-traffic check reads the service's own IAM policy and
  permits direct bindings only for private Cloud Run viewers. It does not read project or folder policy: a
  principal granted `roles/run.invoker` at the project can invoke every Cloud Run service in
  it, this one included, and that cannot be narrowed per service. The boundary this service
  relies on is internal ingress plus no service-level invoker; the routes it mounts keep their
  own authentication.
- **Image pinning.** The deploy resolves the admitted tag to a digest once, deploys
  `repository@digest`, and both release-vector checks expect that digest. It does not yet
  check the image's `org.opencontainers.image.revision` label against the admitted SHA; the
  tag-to-source binding still rests on the train or build-only run that published the tag.
- **Env drift between pump deploys.** The pump derives backend-integration's env, but the
  config train plans only services in `ops/prod.yaml`, which has no pump entry until the
  service exists. Until that entry and a pump leg of `check_cloud_run_env_drift.py` land (with
  step 1's readback), any kill-switch or flag change made on backend-integration must be
  followed by a pump deploy at the same admitted SHA. Release owns that pairing.
- **Headroom gate.** The pump is not in `all`, so trains do not evaluate it. If a caller ever
  passes it to `deploy_headroom.py` it reads 4 of 4 and refuses; it must be excluded there
  (omi-workspace) before anything adds it to a gated service list.
