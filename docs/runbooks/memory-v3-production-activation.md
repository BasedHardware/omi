# Memory `/v3` production activation runbook

**Purpose:** Define the production-only gate after dev-cloud functional proof passes.
**Policy:** Production activation is **NO-GO** until `docs/rollout/memory-v3-proof-order.md` Gate 2 is GO for the exact candidate artifact and independently reviewed.

## Current state

Candidate `1294773c8 feat(memory): wire default-off v3 rollout runtime` is cleared only for local/default-off and dev-cloud preparation.

Production activation remains NO-GO.

A production deployment that declares `MEMORY_V3_GET_ENABLED=false` is
approved only as a dark deployment. This env value does not control request
routing and cannot prove darkness by itself; the code cohort and persisted
control/head/grant state must also remain unactivated.

## Preconditions before this runbook can execute

All must be true:

- Gate 2 dev-cloud evidence bundle exists and is GO.
- Bundle is tied to the exact candidate Git SHA, image digest, index hash, IAM shape, schema, and test runner.
- Independent review accepted the Gate 2 bundle.
- No behavior-affecting code/dependency/config/index/IAM/schema changes occurred since Gate 2; otherwise Gate 2 rerun or explicit reviewer waiver is required.
- Production owner, change window, rollback owner, monitoring owner, and approval artifact are named.

## Scheduler contract before any production deploy

The manual memory-maintenance deploy workflow does not create or mutate Cloud
Scheduler or IAM. It updates the Cloud Run Job and then fails unless the
existing `memory-maintenance-hourly` trigger is:

- `projects/<prod-project>/locations/us-central1/jobs/memory-maintenance-hourly`;
- targeted exactly at
  `https://run.googleapis.com/v2/projects/<prod-project>/locations/us-central1/jobs/memory-maintenance-job:run`;
- `POST`, `0 * * * *`, `Etc/UTC`, and `ENABLED`; and
- configured with a nonempty OAuth service-account email.

Provisioning or repairing this production resource is a separately approved
production write and must happen before dispatching the deploy workflow. The
workflow only runs `gcloud scheduler jobs describe` plus the pure checked-in
validator. If validation fails, the GitHub deployment gate is red even though
the preceding Cloud Run Job update may already have completed.

The enabled Scheduler trigger does not itself activate canonical production
memory. While the checked-in prod job has `MEMORY_MODE=off`, an empty
`MEMORY_ENABLED_USERS`, and
`MEMORY_CANONICAL_MAINTENANCE_ENABLED=false`, each hourly execution exits
without processing a user. These values are maintenance/readiness controls,
not product entitlement; Gate 3 also requires the reviewed code cohort and
persisted controls. Do not pause or delete the Scheduler to represent product
disablement.

## Production-only evidence required

| Artifact | Acceptance condition |
|---|---|
| `prod-candidate-manifest.json` | Git SHA, image digest, deployed revision, production project ID/number, Firestore database ID, runtime service-account unique ID, redacted env values, index-file hash, timestamps. |
| `prod-target-preflight.json` | Explicit production target confirmation; no implicit default project. Confirms this is Gate 3, not Gate 2. |
| `prod-indexes-status.json` | Production required indexes are deployed and READY; actual production query shape is valid. |
| `prod-iam-effective.json` | Production runtime identity and effective IAM verified; no human ADC/Owner/Editor; write permissions only if separately approved for non-GET paths. |
| `prod-config-drift.json` | Production env/config matches approved values; `MEMORY_V3_GET_ENABLED`, `MEMORY_MODE`, and allowlist changes are explicit and auditable. |
| `prod-approval.md` | Human approval, owner groups, expiry/rotation plan, rollback owner, canary UID/cohort, and monitoring owner. |
| `prod-telemetry-readiness.json` | Dashboards/alerts/log sinks ready; redaction verified; stable route/reason/trace fields. |
| `prod-rollback-plan.md` | Kill-switch and env rollback steps, expected propagation bound, owner, and verification commands. |
| `prod-canary-results.json` | Tiny canary results only after approval: success path, fail-closed path, no legacy fallback after selection, zero GET writes, telemetry, rollback. |

## Activation sequence

1. Confirm Gate 2 GO is still valid for this exact candidate.
2. Verify production indexes are READY.
3. Verify production runtime identity and IAM.
4. Verify telemetry/alerting/redaction.
5. Prepare explicit rollback/kill-switch plan.
6. Obtain named human approval.
7. Apply the smallest possible production activation delta:
   - declare `MEMORY_V3_GET_ENABLED=true` only when its proof is approved;
   - declare `MEMORY_MODE=read` only when the deployment is ready;
   - add the tiny cohort to the code-owned entitlement and mirror it in the
     runtime inventory only through reviewed changes;
   - required server-owned control/grant/head/projection docs only through approved production path;
   - **required:** flip the same `MEMORY_*` values on
     `cloud_run.jobs.memory-maintenance-job`
     (`MEMORY_CANONICAL_MAINTENANCE_ENABLED=true`,
     the allowlist, and the already-validated hourly Cloud Scheduler cadence) —
     canonical terminal routing is **not** hosted by `notifications-job`;
   - after separately approved Scheduler provisioning/repair, deploy
     `memory-maintenance-job` via
     `.github/workflows/gcp_memory_maintenance_job.yml`
     (`environment=prod`) and require its post-deploy Scheduler validation to
     pass;
   - confirm live job env and separately verify that an hourly execution can
     invoke `memory-maintenance-job` (same pattern as the
     [dev runbook](memory-v3-dev-cloud-proof.md)).
8. Run tiny canary:
   - confirm the canary UID has known pending short-term work (or seed one);
   - capture a pre-execution baseline (pending ST count / watermark fields only — no raw content);
   - execute `memory-maintenance-job` with `--wait` (or wait for the hourly tick);
   - compare post-state to the baseline and assert watermark / ST→LT movement for the canary UID.
9. If any post-selection prerequisite fails, confirm fail-closed and no legacy fallback.
10. Exercise kill switch / rollback observation as approved.
11. Record evidence and final decision.

`backend/scripts/validate-backend-runtime-env.py` mechanically rejects a
`MEMORY_MODE=read` readiness declaration on request-path surfaces while
`memory-maintenance-job` remains off/maintenance-false. This validates rollout
coordination; it is not the request router. Do not bypass the check for Gate 3.

## Non-claims

Production Gate 3 does not rediscover core behavior already proven in dev-cloud. It validates production-specific deltas only:

- production identity;
- production indexes;
- production config/drift;
- production telemetry/rollback ownership;
- production canary on approved cohort.

If core behavior appears different in production, stop and treat as NO-GO; do not debug by widening production exposure.

## Immediate stop conditions

Stop and roll back if any occurs:

- request hits unexpected revision/image;
- unexpected project ID/number/database ID;
- runtime identity mismatch;
- canonical memory path selected for non-allowlisted UID;
- client-supplied UID/mode/header affects route selection;
- post-selection failure invokes legacy;
- any GET writes or attempts writes;
- cross-user data/cursor leakage;
- memory content/token/raw cursor appears in logs/headers;
- kill switch does not block within documented propagation bound;
- telemetry/alerts unavailable during canary;
- evidence cannot be tied to exact candidate.
