# Memory `/v3` dev-cloud proof runbook

**Purpose:** Prove enabled canonical `GET /v3/memories` behavior in a dedicated non-production Firebase/GCP project before any production activation.
**Policy:** See `docs/rollout/memory-v3-proof-order.md`.

## Non-negotiable boundary

Gate 2 must exercise a deployed branch backend revision using the actual runtime identity and deployment mechanism.

A local backend using dev credentials is useful for debugging only. It is supplemental evidence and cannot satisfy the dev-cloud gate.

Do not use production with a synthetic UID and call it dev-cloud.

## Checked-in preparation tooling

Use `backend/scripts/v3_dev_cloud_readiness.py` to prepare and validate the local artifact contract before a real dev-cloud run. The script is safe by default: it performs no network calls, no Firestore reads, and no Firestore writes.

Default preflight:

```bash
cd backend
python3 scripts/v3_dev_cloud_readiness.py
```

Expected status without a fully specified dev target is `BLOCKED` with missing-env blockers. This is correct and is not a failure.

## First-user dev read-mode persistence

The first-user dev/beta read proof uses deploy plane `based-hardware-dev` and runtime data/auth Firestore project `based-hardware`.

Checked-in dev runtime config intentionally preserves the first-user full canonical baseline across future dev deploys:

```text
MEMORY_MODE=read
MEMORY_ENABLED_USERS=vi7SA9ckQCe4ccobWNxlbdcNdC23
# Next dogfood (re-enable soon): ,viUv7GtdoHXbK1UBCDlPuTDuPgJ2
MEMORY_V3_GET_ENABLED=true
# Request-path CRON stays false; only memory-maintenance-job sets CRON=true.
MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=false   # request-path / GKE
MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED=true
# memory-maintenance-job: MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=true
```

Dev dogfood cohort (code `CANONICAL_MEMORY_USERS` + env allowlist):

- `vi7SA9ckQCe4ccobWNxlbdcNdC23` — david.d.zhang@gmail.com (active)
- `viUv7GtdoHXbK1UBCDlPuTDuPgJ2` — kodjima33@gmail.com (commented out for this PR; re-enable soon)

Promotion/consolidation maintenance runs from the dedicated hourly `memory-maintenance-job` Cloud Run Job (not request-path backend, not `notifications-job`). That job is part of `backend/deploy/runtime_env.yaml` and is deployed via `.github/workflows/gcp_memory_maintenance_job.yml` (manual) and `.github/workflows/gcp_memory_maintenance_job_auto_dev.yml` (auto on push to `main` for `backend/**`) with the same whitelist-scoped `MEMORY_*` flags plus consolidation secrets (`OPENAI_API_KEY`, Pinecone, Typesense, `SERVICE_ACCOUNT_JSON`).

### Post-merge dogfood checklist (dev only)

1. Confirm auto-dev ran after merge (or dispatch: `gh workflow run "Deploy Memory Maintenance Job to Cloud RUN" -f environment=development -f branch=main`).
2. Confirm live job env has `MEMORY_MODE=read`, cron/fast-track `true`, and secrets present.
3. Capture a pre-execution baseline for the active dogfood UID (pending ST count / last watermark fields only — no raw memory content).
4. Execute once and wait: `gcloud run jobs execute memory-maintenance-job --region=us-central1 --project=based-hardware-dev --wait`
5. Assert watermark / ST→LT movement vs the baseline for UID `vi7SA9ckQCe4ccobWNxlbdcNdC23` (do not print raw memory content).
6. Create or update Cloud Scheduler to run the job hourly (manual GCP; not IaC in-repo):

```bash
# Create (first time) — adjust SA email to the Cloud Run Job runtime identity used in based-hardware-dev
gcloud scheduler jobs create http memory-maintenance-hourly \
  --location=us-central1 \
  --project=based-hardware-dev \
  --schedule="0 * * * *" \
  --time-zone=UTC \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/based-hardware-dev/jobs/memory-maintenance-job:run" \
  --http-method=POST \
  --oauth-service-account-email="<JOB_RUNTIME_SA>@based-hardware-dev.iam.gserviceaccount.com"

# Or update an existing scheduler target to the same URI
gcloud scheduler jobs update http memory-maintenance-hourly \
  --location=us-central1 \
  --project=based-hardware-dev \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/based-hardware-dev/jobs/memory-maintenance-job:run"
```

Do **not** dispatch `notifications-job` for memory maintenance.
Its independent deploy workflow explicitly removes only stale canonical-maintenance and Typesense bindings left by historical revisions. It merges the declared notification/X-sync config so unrelated live dependencies are not globally overwritten.

This is dev-only. Production remains `MEMORY_MODE=off`, `MEMORY_ENABLED_USERS=""`, `MEMORY_V3_GET_ENABLED=false`, and promotion cron/fast-track disabled on `memory-maintenance-job`. Non-whitelisted users stay on legacy memory with Desktop lifecycle UI fail-closed.

## First-user projection operator

Use `backend/scripts/apply_first_user_v3_projection.py` to build the first-user compatibility projection from existing canonical `memory_items`. Dry-run is the default and prints only doc paths, IDs, generations, fences, field names, and content lengths.

Dry-run:

```bash
cd backend
python3 scripts/apply_first_user_v3_projection.py \
  --uid vi7SA9ckQCe4ccobWNxlbdcNdC23 \
  --project based-hardware \
  --limit 25
```

Apply one known memory only after reviewing the dry-run:

```bash
cd backend
python3 scripts/apply_first_user_v3_projection.py \
  --uid vi7SA9ckQCe4ccobWNxlbdcNdC23 \
  --project based-hardware \
  --memory-id <memory-id> \
  --apply \
  --confirm-uid vi7SA9ckQCe4ccobWNxlbdcNdC23
```

The script writes only:

```text
users/{uid}/v3_compatibility_projection/state
users/{uid}/v3_compatibility_projection_items/{memory_id}
```

It refuses cross-user docs, non-active/tombstoned/archive rows, restricted sensitivity labels, and generation/fence mismatches with `users/{uid}/memory_state/head`. Output includes a rollback manifest listing the exact touched projection doc paths; rollback means deleting or restoring only those listed paths from a known-good backup. The script does not write rollout gates, user control state, env vars, vectors, or production data.

## First-user read-only E2E proof

Use `backend/scripts/first_user_memory_e2e_proof.py` after projection docs and dev read gates are expected to be ready. The script is read-only: it performs Firestore reads plus authenticated/unauthenticated `GET /v3/memories` calls, and it redacts memory content and tokens.

```bash
cd backend
python3 scripts/first_user_memory_e2e_proof.py \
  --uid vi7SA9ckQCe4ccobWNxlbdcNdC23 \
  --project based-hardware \
  --backend-url <dev-backend-url> \
  --id-token-file /path/to/firebase-id-token.txt \
  --limit 10
```

The proof checks:

- global read gate open and kill switch clear;
- write convergence gate ready;
- user control state `mode=read` with `grants.omi_chat.default_memory=true`;
- `memory_state/head` exists;
- projection state/items exist and match head generation/fences;
- authenticated `/v3/memories` returns 200 for only the requested UID;
- canonical lifecycle fields such as `layer`/`memory_tier` are present when items are returned;
- unauthenticated `/v3/memories` fails 401/403.

## Repair a legacy-shaped V3 state head

If `/v3/memories` fails because `users/{uid}/memory_state/head` still has
legacy-ledger fields but no valid trusted V3 fields, use the scoped repair
after the backend containing it is deployed. It reads the canonical
`memory_state/apply_control` document and writes only the six trusted head
metadata fields; it does not read or write memory content, projection items,
rollout gates, or vectors.

```bash
cd backend
python3 scripts/repair_memory_state_head.py \
  --uid <uid> \
  --firestore-project based-hardware
```

The default command is a dry run. Confirm that it reports `repair_required`,
then use the explicit confirmation to apply and revalidate the V3 trust
contract:

```bash
python3 scripts/repair_memory_state_head.py \
  --uid <uid> \
  --firestore-project based-hardware \
  --apply \
  --confirm-uid <uid>
```

If it reports `blocked_invalid_apply_control`, stop: the canonical apply
control state is not trustworthy enough to derive a repair.

Search, vector, MCP/developer, and other default-read surfaces are reported as `not_checked` unless a route-specific harness is added. Do not treat a passing first-user `/v3/memories` proof as full Gate 2 GO.

Prepare a local evidence-bundle skeleton for the deployed dev-cloud CI/proof job to fill:

```bash
cd backend
python3 scripts/v3_dev_cloud_readiness.py \
  --run-id <run-id> \
  --uid-a <synthetic-dev-uid-a> \
  --uid-b <synthetic-dev-uid-b> \
  --write-bundle-dir /tmp/memory-v3-dev-cloud-<git-sha>-<run-id>
```

Required env for `READY_TO_EXECUTE_DEV_CLOUD_PROOF` preflight:

```text
MEMORY_DEV_CLOUD_PROJECT_ID=<non-prod project id>
MEMORY_DEV_CLOUD_PROJECT_NUMBER=<non-prod project number>
GOOGLE_CLOUD_PROJECT=<same non-prod project id>
GOOGLE_CLOUD_PROJECT_NUMBER=<same non-prod project number>
MEMORY_DEV_CLOUD_DATABASE_ID=<database id, often (default)>
MEMORY_DEV_CLOUD_REGION=<region>
MEMORY_DEV_CLOUD_BACKEND_URL=<deployed branch backend URL>
MEMORY_DEV_CLOUD_DEPLOYED_REVISION=<deployed revision>
MEMORY_DEV_CLOUD_IMAGE_DIGEST=<image digest>
MEMORY_DEV_CLOUD_RUNTIME_SERVICE_ACCOUNT=<runtime service account>
MEMORY_DEV_CLOUD_FIXTURE_WRITER_PRINCIPAL=<separate fixture writer identity>
MEMORY_PRODUCTION_PROJECT_IDS=<comma-separated prod project ids to reject>
MEMORY_PRODUCTION_PROJECT_NUMBERS=<comma-separated prod project numbers to reject>
```

`READY_TO_EXECUTE_DEV_CLOUD_PROOF` means only that local target metadata is complete and not obviously production. It is **not** Gate 2 GO. Gate 2 GO requires the deployed backend proof suite to fill and pass the bundle described below.

## Required identities

| Identity | Purpose | Required constraints |
|---|---|---|
| Runtime service account | Deployed backend revision serving `/v3/memories` | Read-only Firestore access required for canonical-memory GET; no Firestore data create/update/delete permissions. No human ADC. No Owner/Editor. |
| Fixture writer identity | Creates synthetic control/head/projection docs | Separate from runtime identity. Dev project only. Hard-stops on production project ID/number. |
| Test caller identity | Obtains synthetic Firebase auth tokens | Synthetic users only. No real user data. |

## Mandatory evidence bundle

Produce one immutable bundle named like:

```text
memory-v3-dev-cloud-<git-sha>-<run-id>.tar.gz
```

(Legacy bundles may use the `memory-v3-dev-cloud-…` prefix; tooling accepts both during transition.)

The bundle must exclude credentials, bearer tokens, private keys, raw memory text from real users, and production identifiers beyond allowed project metadata.

Required files:

| Artifact | Required contents / acceptance condition |
|---|---|
| `candidate-manifest.json` | Git SHA, clean-tree assertion, image digest, deployed revision, build workflow/run, test-runner SHA, backend URL, dev project ID/number, Firestore database ID, region, runtime service-account unique ID, fixture-writer identity, redacted env values, index-file SHA-256, timestamps. |
| `target-preflight.json` | Expected and actual project ID, project number, database ID, credential principal, environment. Must prove commands abort for known production project IDs/numbers and reject implicit default projects. |
| `deployment.json` | Deployed branch revision, image digest, runtime identity, deployment command/workflow, runtime-emitted revision identifier proving requests hit that revision. |
| `indexes-source.json` | Exact checked-in `firestore.indexes.json` and hash. |
| `indexes-status.json` | Dev database deployed index listing and READY status; successful execution of actual projection query. Deployment completion alone is insufficient. |
| `iam-effective.json` | Effective permissions for runtime and fixture-writer identities, including inherited grants. Runtime must not have Firestore data-write permissions. |
| `auth-evidence.json` | Synthetic Firebase users, token issuer/audience validation, server-observed authenticated UID, and proof client fields do not select UID. Use at least two synthetic users. |
| `fixtures.redacted.json` | Run-scoped document paths and schema-valid synthetic values for global read gate, kill switch clear, convergence satisfied, user grant, authoritative head generation, projection state/items. Include setup/cleanup manifests and before/after hashes. |
| `proof-results.json` | One result per mandatory proof case, no skips. Include test ID, trace ID, authenticated UID, route decision, legacy invocation count, canonical-memory Firestore adapter read count, canonical-memory Firestore write/attempt count, HTTP result, stable reason/error code, assertion outcome. |
| `junit.xml` | CI/JUnit output for the proof suite. |
| `http-transcripts.redacted.ndjson` | Requests/responses for proof cases with tokens removed. Include route-selection diagnostics and allowed headers. |
| `memory-operations.ndjson` | Canonical-memory Firestore adapter operation records correlated by trace ID (legacy filename retained). Primary evidence for zero off-path operations and zero GET writes. |
| `audit-extract.ndjson` | Supporting Firestore Data Access audit records where enabled, filtered to runtime principal and test interval. Supporting only, not the sole proof. |
| `telemetry-redaction-report.json` | Required fields present; auth tokens, raw cursors, memory text, and sensitive payloads absent. No production sink claim. |
| `rollback-report.json` | Positive request before rollback, kill-switch change, first observed fail-closed request, propagation time, warm-instance repeated requests, restoration, positive request after restoration. |
| `cleanup-report.json` | Synthetic users/docs removed or intentionally retained under expiration policy; no unexpected doc changes; no residual activation flags or allowlist entries. |
| `checksums.sha256` | Hash every evidence file. |
| `review.md` | Mandatory-test count, explicit `GO` / `NO_GO` / `BLOCKED`, open production-only blockers, independent reviewer acceptance. |

## Mandatory proof matrix

Use one valid baseline and mutate one prerequisite at a time.

| Case | Required result |
|---|---|
| Feature variable absent, false, or non-exact | Canonical memory path not selected; zero canonical-memory adapter calls; existing legacy/off contract unchanged. |
| `MEMORY_MODE` not exactly `read` | Canonical memory path not selected; zero canonical-memory adapter calls. |
| Authenticated UID not allowlisted | Canonical memory path not selected; no canonical-memory Firestore calls. |
| Valid allowlisted user | Exact synthetic memories, ordering, pagination, generation, and headers expected by API contract. |
| Client UID/query/body/mode/header spoof | No effect on authenticated UID or route selection. |
| User A attempts to reference user B | No B data returned through query, header, path, or cursor. |
| Global gate absent/disabled | Canonical memory path selected, then fail closed; legacy invocation count zero. |
| Kill switch active | Fail closed; legacy invocation count zero. |
| Grant missing | Fail closed; legacy invocation count zero. |
| Write convergence absent/false | Fail closed; legacy invocation count zero. |
| Head missing or malformed | Fail closed; legacy invocation count zero. |
| Head/projection generation mismatch | Fail closed; legacy invocation count zero. |
| Projection missing or malformed | Fail closed; legacy invocation count zero. |
| Cursor malformed/tampered/stale-generation/from another user | Stable error/client result; no legacy fallback; no cross-user disclosure. |
| Runtime Firestore read permission denied | Fail closed; no legacy fallback. |
| Firestore timeout/unavailable | Fail closed through existing dependency-injection tests; no public bypass endpoint. |
| Every GET case | Zero successful or attempted canonical-memory writes. |
| Real projection query | Succeeds against dev Firestore with checked-in index set deployed and READY. |
| Telemetry | Route/reason/trace fields present; memory content, tokens, and cursor payload absent. |
| Kill-switch rollback | Blocks within documented maximum propagation interval without redeployment. |

## Read/write evidence definition

If legacy/off paths read Firestore, do not claim zero total Firestore reads. The enforceable assertion is:

> Zero canonical-memory Firestore adapter calls and no additional reads relative to the captured legacy baseline.

For every GET case, require zero canonical-memory Firestore writes and zero attempted writes.

## Dev-cloud blockers

These block dev-cloud GO:

- no dedicated dev project, deployed branch backend, real dev Auth, or real dev Firestore access;
- dev indexes not READY or not traceable to `firestore.indexes.json`;
- runtime identity has write permission or uses human/admin credentials;
- missing project-ID/project-number production hard stop;
- no separate safe synthetic fixture writer;
- missing authoritative head/projection/convergence synthetic fixtures;
- ambiguous route-selection/failure boundary;
- weak evidence for zero canonical-memory writes/off-path operations;
- unproven auth spoofing, cross-user isolation, or cursor isolation;
- kill switch cannot be exercised or has unbounded propagation;
- logs leak memory content, tokens, cursors, or sensitive values;
- evidence is not tied to exact candidate build/config.

## Production-only blockers after dev-cloud GO

After Gate 2 GO, these remain production activation blockers rather than dev-cloud blockers:

- production indexes READY;
- production runtime identity/IAM;
- production credentials/access;
- production control docs and allowlist;
- production convergence/head/projection readiness;
- production telemetry sinks, dashboards, alerts;
- production owner, approval, change window, and rollback authority;
- production tiny canary;
- production quota and real-data behavior.

Rule of thumb:

> A blocker may become prod-only only when it concerns a production-specific identity, resource, data state, operational owner, or approval. A blocker concerning program behavior, authorization, failure semantics, evidence quality, or environment isolation remains a dev-cloud blocker.

## Unsafe shortcuts prohibited

- Using production project with synthetic UID and calling it dev-cloud.
- Accepting local backend + dev credentials as mandatory cloud proof.
- Running backend under human ADC, Owner, Editor, or fixture-writer identity.
- Temporarily granting write/admin access to the runtime identity and removing it after tests.
- Treating Firestore client rules as backend IAM evidence.
- Inferring target project from ambient credentials/default Firebase project.
- Adding client headers, query params, or test endpoints that bypass gates.
- Manually modifying indexes without updating and hashing checked-in index file.
- Starting positive tests while indexes are still building.
- Turning the inert rollout config generator into an activation tool. Use a separate dev-only synthetic fixture tool with hard project-number checks.
- Enabling wildcard allowlists, default-memory grants, or broad cohorts for testing.
- Combining multiple missing prerequisites in one negative proof case.
- Inferring zero reads/writes from successful responses or absence of errors.
- Restoring legacy fallback after canonical memory has been selected.
- Copying production memory docs, tokens, UIDs, logs, or cursors into dev.
- Sharing mutable fixtures between concurrent runs without a run namespace.
- Reusing a GO bundle after runtime code, dependencies, image digest, index definitions, auth, IAM, schema, query, or gate semantics change.
