# Memory `/v3` proof-order policy

**Status:** Normative rollout gate for canonical `GET /v3/memories` activation.
**Current candidate:** `1294773c8 feat(memory): wire default-off v3 rollout runtime`
**Oracle review:** Strategy change reviewed; decision was **GO to adopt non-production-first strategy**, **GO to begin dev-cloud environment/tooling work**, **NO-GO for dev-cloud functional proof until P0 artifacts pass**, and **NO-GO for production activation**.

Production **must not** be the first environment in which the enabled `GET /v3/memories` path is exercised against a real cloud Firestore database.

## Gate 1 — Local/emulator proof

Gate 1 proves code-path behavior using unit tests, fake Firestore, Firebase emulator where applicable, and hermetic E2E tests.

Gate 1 may prove:

- default-off behavior;
- exact server-side route-selection conditions;
- fail-closed behavior after canonical memory selection;
- no legacy fallback after canonical memory selection;
- absence of canonical-memory writes in tested GET paths;
- local query/index contract shape.

Gate 1 must not claim:

- real cloud runtime behavior;
- deployed runtime identity binding;
- real cloud IAM least privilege;
- real deployed index readiness;
- production telemetry sink/alert readiness;
- production approval or rollout readiness.

## Gate 2 — Dev-cloud functional and safety proof

Gate 2 is mandatory before any production activation.

Gate 2 must use:

- a dedicated non-production Firebase/GCP project;
- synthetic authenticated users and synthetic memory data only;
- a deployed branch backend revision using its actual runtime identity and deployment mechanism;
- the exact candidate source revision and recorded image digest;
- the repository's checked-in Firestore index definition;
- a runtime identity with required read permissions and no Firestore data-write permissions;
- a separate dev-only fixture-writer identity;
- explicit project-ID, project-number, database-ID, and environment checks that abort on a production target.

A backend running locally with dev-cloud credentials may supplement Gate 2, but must not satisfy Gate 2.

Gate 2 is GO only when:

- the mandatory proof matrix passes without skips;
- required dev Firestore indexes are READY;
- the real projection query succeeds in dev Firestore;
- off/pre-selection requests perform zero canonical-memory Firestore adapter operations;
- all GET cases perform zero canonical-memory writes or attempted writes;
- post-selection prerequisite failures fail closed and do not invoke legacy behavior;
- authorization and cross-user isolation are demonstrated with at least two synthetic users;
- telemetry/headers/logs are traceable and redacted;
- kill-switch rollback succeeds within its documented propagation bound;
- the evidence bundle is tied to the exact candidate artifact and independently reviewed.

Gate 2 GO means **dev-cloud functional proof passed**. It does not approve production activation.

## Canonical memory selection and fallback boundary

The canonical memory path is selected only for a valid authenticated UID in
the code-owned `CANONICAL_MEMORY_USERS` cohort. The request then reads the
persisted control/head/grant/projection state and fails closed unless every
read prerequisite is satisfied. `MEMORY_V3_GET_ENABLED`, `MEMORY_MODE`, and
`MEMORY_ENABLED_USERS` are deploy-readiness declarations validated across
surfaces; request routing does not read them and they cannot grant or revoke
product entitlement.

A user outside the code-owned cohort retains the documented legacy behavior
and must not invoke the canonical-memory Firestore adapter.

After canonical memory selection, failure of any global gate, kill switch, user grant, write-convergence prerequisite, authoritative head, generation check, projection read, cursor validation, IAM read, or other rollout prerequisite must fail closed and must not invoke the legacy path.

Client-supplied UID, mode, headers, body fields, or query parameters must not change authentication, allowlist membership, or route selection.

## Gate 3 — Production activation proof

No production activation variable, production allowlist entry, global or per-user rollout document, memory grant, or production canary may be changed until Gate 2 is GO for the exact candidate artifact and the evidence bundle has been independently reviewed.

Gate 3 is limited to production-specific deltas:

- production indexes READY;
- production runtime identity and effective IAM;
- production configuration and drift verification;
- production telemetry sinks, dashboards, alerts, owner, and rollback authority;
- approved tiny canary;
- production rollback execution and observation.

A production deployment with the `MEMORY_V3_GET_ENABLED=false` readiness
declaration is approved only as a dark deployment. The value is not a request
gate and does not by itself prove darkness; the code cohort and persisted
controls must also remain unactivated. Production index deployment while the
runtime remains default-off may occur only under separate approval and does not
satisfy Gate 2.

## Evidence validity

A Gate 2 evidence bundle must identify:

- Git SHA;
- clean-tree state;
- image digest;
- deployed revision;
- project ID and project number;
- Firestore database ID;
- runtime identity;
- environment configuration;
- index-definition hash;
- fixture run ID;
- test runner revision.

Changes to runtime code or dependencies, image digest, authentication, environment parsing, index definitions, Firestore schema or query shape, IAM, gate semantics, or rollback behavior invalidate Gate 2 GO and require a rerun. A reviewer may record a waiver only for demonstrably non-behavioral changes.

The only gate statuses are `NOT_RUN`, `BLOCKED`, `NO_GO`, and `GO`. `PRE_GCP_READY` is a preparation status and is not Gate 2 GO.

## Current candidate decision

Candidate: `1294773c8 feat(memory): wire default-off v3 rollout runtime`

- **Local/emulator gate:** GO to proceed to dev-cloud setup, based on recorded unit, hermetic E2E, configuration, and default-off evidence. This is not a cloud-runtime claim.
- **Dev-cloud gate:** BLOCKED / NOT_RUN pending a dedicated dev project, deployed branch revision, dev index readiness, read-only runtime identity, synthetic fixture tooling, real-auth proof suite, operation evidence, and rollback evidence.
- **Production activation gate:** NO-GO by policy until dev-cloud GO and independent review.
- Any prior clearance for default-off production code or index declaration is non-activation plumbing only and must not be treated as enabled-path proof.

## Human dogfood lane paused

No human UID is currently approved for the canonical-memory, Smart Tasks, or
Chat-first cohort. Checked-in dev runtime config must remain fail-closed:

- `MEMORY_MODE=off`;
- `MEMORY_ENABLED_USERS=`;
- `MEMORY_V3_GET_ENABLED=false`;
- `MEMORY_CANONICAL_MAINTENANCE_ENABLED=false`;
- parity capture disabled with an empty principal allowlist.

Hourly canonical maintenance (required normalization → TTL audit → one terminal
consolidation route per pending item) is hosted by `memory-maintenance-job` and
must remain disabled until a separately reviewed rollout restores a cohort;
Cloud Scheduler owns cadence.
Production declarations must remain off with an empty runtime inventory and
`MEMORY_V3_GET_ENABLED=false`, while the production code cohort and persisted
controls remain unactivated, until Gate 2 and Gate 3 requirements are
satisfied. Gate 3 must update `cloud_run.jobs.memory-maintenance-job` together
with request-path readiness declarations; `validate-backend-runtime-env.py`
fails if request-path `MEMORY_MODE=read` is declared while the job stays off.

First-user projection tooling may write only the compatibility projection state/items for the same UID after an explicit apply confirmation. Its dry-run and apply output must redact content and include a rollback manifest with exact touched doc paths. The first-user E2E proof is read-only and must report non-`/v3/memories` read surfaces as `not_checked` when they cannot be generically exercised.

This first-user lane can improve launch confidence and dogfooding, but it is not a substitute for Gate 2 dev-cloud GO because it uses a real first-user UID rather than the full synthetic multi-user proof matrix.
