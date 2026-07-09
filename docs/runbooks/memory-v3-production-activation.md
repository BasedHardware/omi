# Memory `/v3` production activation runbook

**Purpose:** Define the production-only gate after dev-cloud functional proof passes.
**Policy:** Production activation is **NO-GO** until `docs/rollout/memory-v3-proof-order.md` Gate 2 is GO for the exact candidate artifact and independently reviewed.

## Current state

Candidate `1294773c8 feat(memory): wire default-off v3 rollout runtime` is cleared only for local/default-off and dev-cloud preparation.

Production activation remains NO-GO.

A production deployment with `MEMORY_V3_GET_ENABLED` absent or false is a dark deployment only. It does not prove enabled behavior and must not be cited as functional proof.

## Preconditions before this runbook can execute

All must be true:

- Gate 2 dev-cloud evidence bundle exists and is GO.
- Bundle is tied to the exact candidate Git SHA, image digest, index hash, IAM shape, schema, and test runner.
- Independent review accepted the Gate 2 bundle.
- No behavior-affecting code/dependency/config/index/IAM/schema changes occurred since Gate 2; otherwise Gate 2 rerun or explicit reviewer waiver is required.
- Production owner, change window, rollback owner, monitoring owner, and approval artifact are named.

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
   - exact `MEMORY_V3_GET_ENABLED=true` only when approved;
   - exact `MEMORY_MODE=read` only when approved;
   - one/small approved allowlist entry only;
   - required server-owned control/grant/head/projection docs only through approved production path;
   - **required:** flip the same `MEMORY_*` values on `cloud_run.jobs.memory-maintenance-job` (cron + fast-track + allowlist) — ST→LT is **not** hosted by `notifications-job`;
   - deploy `memory-maintenance-job` via `.github/workflows/gcp_memory_maintenance_job.yml` (`environment=prod`) and confirm live job env;
   - create/update Cloud Scheduler → Run Job Execute hourly for prod `memory-maintenance-job` (same pattern as the [dev runbook](memory-v3-dev-cloud-proof.md)).
8. Run tiny canary (include at least one ST→LT maintenance execute or wait for the hourly tick and assert watermark movement for the canary UID).
9. If any post-selection prerequisite fails, confirm fail-closed and no legacy fallback.
10. Exercise kill switch / rollback observation as approved.
11. Record evidence and final decision.

`backend/scripts/validate-backend-runtime-env.py` mechanically rejects `MEMORY_MODE=read` on request-path surfaces while `memory-maintenance-job` remains off/cron-false. Do not bypass that check for Gate 3.

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
