# V17 /v3 dev-cloud proof runbook

**Purpose:** Prove enabled V17 `GET /v3/memories` behavior in a dedicated non-production Firebase/GCP project before any production activation.  
**Policy:** See `docs/rollout/v17-v3-proof-order.md`.

## Non-negotiable boundary

Gate 2 must exercise a deployed branch backend revision using the actual runtime identity and deployment mechanism.

A local backend using dev credentials is useful for debugging only. It is supplemental evidence and cannot satisfy the dev-cloud gate.

Do not use production with a synthetic UID and call it dev-cloud.

## Required identities

| Identity | Purpose | Required constraints |
|---|---|---|
| Runtime service account | Deployed backend revision serving `/v3/memories` | Read-only Firestore access required for V17 GET; no Firestore data create/update/delete permissions. No human ADC. No Owner/Editor. |
| Fixture writer identity | Creates synthetic control/head/projection docs | Separate from runtime identity. Dev project only. Hard-stops on production project ID/number. |
| Test caller identity | Obtains synthetic Firebase auth tokens | Synthetic users only. No real user data. |

## Mandatory evidence bundle

Produce one immutable bundle named like:

```text
v17-v3-dev-cloud-<git-sha>-<run-id>.tar.gz
```

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
| `proof-results.json` | One result per mandatory proof case, no skips. Include test ID, trace ID, authenticated UID, route decision, legacy invocation count, V17 Firestore adapter read count, V17 Firestore write/attempt count, HTTP result, stable reason/error code, assertion outcome. |
| `junit.xml` | CI/JUnit output for the proof suite. |
| `http-transcripts.redacted.ndjson` | Requests/responses for proof cases with tokens removed. Include route-selection diagnostics and allowed headers. |
| `v17-operations.ndjson` | V17 Firestore adapter operation records correlated by trace ID. Primary evidence for zero V17 off-path operations and zero GET writes. |
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
| Feature variable absent, false, or non-exact | V17 not selected; zero V17 adapter calls; existing legacy/off contract unchanged. |
| `V17_MODE` not exactly `read` | V17 not selected; zero V17 adapter calls. |
| Authenticated UID not allowlisted | V17 not selected; no V17 Firestore calls. |
| Valid allowlisted user | Exact synthetic memories, ordering, pagination, generation, and headers expected by API contract. |
| Client UID/query/body/mode/header spoof | No effect on authenticated UID or route selection. |
| User A attempts to reference user B | No B data returned through query, header, path, or cursor. |
| Global gate absent/disabled | V17 selected, then fail closed; legacy invocation count zero. |
| Kill switch active | Fail closed; legacy invocation count zero. |
| Grant missing | Fail closed; legacy invocation count zero. |
| Write convergence absent/false | Fail closed; legacy invocation count zero. |
| Head missing or malformed | Fail closed; legacy invocation count zero. |
| Head/projection generation mismatch | Fail closed; legacy invocation count zero. |
| Projection missing or malformed | Fail closed; legacy invocation count zero. |
| Cursor malformed/tampered/stale-generation/from another user | Stable error/client result; no legacy fallback; no cross-user disclosure. |
| Runtime Firestore read permission denied | Fail closed; no legacy fallback. |
| Firestore timeout/unavailable | Fail closed through existing dependency-injection tests; no public bypass endpoint. |
| Every GET case | Zero successful or attempted V17 writes. |
| Real projection query | Succeeds against dev Firestore with checked-in index set deployed and READY. |
| Telemetry | Route/reason/trace fields present; memory content, tokens, and cursor payload absent. |
| Kill-switch rollback | Blocks within documented maximum propagation interval without redeployment. |

## Read/write evidence definition

If legacy/off paths read Firestore, do not claim zero total Firestore reads. The enforceable assertion is:

> Zero V17 Firestore adapter calls and no additional reads relative to the captured legacy baseline.

For every GET case, require zero V17 Firestore writes and zero attempted writes.

## Dev-cloud blockers

These block dev-cloud GO:

- no dedicated dev project, deployed branch backend, real dev Auth, or real dev Firestore access;
- dev indexes not READY or not traceable to `firestore.indexes.json`;
- runtime identity has write permission or uses human/admin credentials;
- missing project-ID/project-number production hard stop;
- no separate safe synthetic fixture writer;
- missing authoritative head/projection/convergence synthetic fixtures;
- ambiguous route-selection/failure boundary;
- weak evidence for zero V17 writes/off-path operations;
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
- Restoring legacy fallback after V17 has been selected.
- Copying production memory docs, tokens, UIDs, logs, or cursors into dev.
- Sharing mutable fixtures between concurrent runs without a run namespace.
- Reusing a GO bundle after runtime code, dependencies, image digest, index definitions, auth, IAM, schema, query, or gate semantics change.
