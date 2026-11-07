## What changed and why

Add sticky directory enrollment before signup telemetry, fail-closed HTTP/WS plane resolution, generation-zero cell cutovers, and the required cell/directory account-wipe step. Routing ships off; this PR authorizes no cell serving or positive enrollment ramp.

Round-1 review fixes prevent stale open cutover reads from publishing an idle cache entry and prevent stale routes from recreating wiped cell data. Redis epochs plus a pending-writer guard protect both Firestore write seams; the cell space-head lock guards mutation/replay, cursor, epoch, enrollment and purge paths. Wipe retains a content-free tombstone and retries safely after fencing.

D5 waiver (lead fix-r1 ruling): B2 ships dark with no runtime_env PG bindings. Exact host/database/IAM identities belong to the provisioning PR, gated on the N2 connection-budget measurement. The deploy validator now rejects partial enablement across backend, backend-sync, backend-sync-backfill, backend-listen and pusher. DIRECTORY and CELLS bindings are required on every surface because every enrollment dependency can initialize a cell head; backend also runs account wipe. DSN or complete IAM bindings and explicit pool sizes 1..2 are supported. No infrastructure values were guessed. The earlier ANX values ask `event:ev_77757863d2f3cbfc70593225b023691f` is superseded by this ruling.

## Product invariants affected

INV-CUTOVER-1, INV-DATA-1, INV-MEM-3. Extend the existing cutover control record rather than introducing another authority. Bridge generation fencing, auth/control reachability and destination-binding honesty remain intact. Migrating allows reads and denies mutations; migrated allows cell traffic at generation zero while legacy writes remain fenced. Cell/directory wipe failures remain required failures before Firestore deletion. The lead owns the separate locked-invariant revision note for migrated; invariant files are unchanged.

## How it was verified

Local tests only, with GOOGLE_APPLICATION_CREDENTIALS and every CLOUDSDK_* variable unset (also SERVICE_ACCOUNT_JSON and FIREBASE_AUTH_CREDENTIALS_PATH). Python is this worktree's backend/.venv (3.11.15); heavy runs use omi-heavy. No GCP tier, production access, or api.omi.me calls. Current round-1 results:

- Real local Postgres: directory router, cell wipe, directory store and cell conformance: 68 passed, no skips.
- Cutover foundation and M9 plane probes: 88 passed.
- Runtime deployment validator, including positive/negative binding fixtures: 198 passed (included in the final 503-test deploy run).
- Registry renderer/checker passed. Final generated output keeps origin/main's as-of date (2026-11-05), removing unrelated overdue churn; only B2 entries differ.
- Async blocker scan passed with zero findings.
- Deployment verification passed: 503 deploy tests plus 36 source-admission tests. Backend environment preflight: 17 passed, 9 optional warnings, zero failures.
- Enforced backend typecheck passed: zero errors. Frozen local preflight passed all 46 checks in 470.69 seconds; the resulting product tree is committed as 6c194bfa7d35.
- Named witnesses: 3,073 passed, one intentional referral skip; real-PG conformance is included above. The first full 2,677-file selector had 11 nonzero files. Nine passed guarded replays (259 tests); the remaining results are an unchanged main-branch monitoring contract failure and the known 900-second cross-service timeout. The final source selector covered all 2,677 files (checkpoint 186 + resumed 2,491), verified by exact path-set equality: 2,670 nonfailing files and seven nonzero files. Those seven are monitoring contract, executors, fleet deployment, cross-service timeout, Soniox capture-axis, Soniox wire metrics, and speaker prompts. The three additional guarded replays passed all 93 tests (24 + 11 + 58), with standard assertions, 100-ms waits, file isolation and CPU guards intact. No full-suite green claim is made.
- Firestore emulator integration: 107 skipped because no loopback emulator was available; no deployed acceptance is claimed.

The monitoring failure is on the pinned qualification base `4b1c40b5ef03`; PR #24804 fixed it on main while the final replay waited. No second rebase was performed after freezing the qualified product tree.

Exact commands and counts: `.agent-artifacts/pgf/b2-result.md`. `.agent-artifacts/pgf-result.md` matches origin/main and is owned by another PR.

Operations runbook (future authorized provisioning/integration work):

1. B1 (#24790) precedes B2. Deploy B2 with DIRECTORY_ROUTING_MODE off everywhere. Apply directory and cell migrations, including cells/0002_write_fence.sql, on staging before enabling routing. Only enrollment/backfill creates cell heads; writes never auto-create them, and tombstones cannot be revived.
2. O4: write new-owner-cell1 via backend/scripts/rollout/ramp_set.py only after every _ramp reader knows the name (backend, backend-listen, pusher, backend-sync and notifications-job). Older readers reject the whole document and freeze other ramps at last-known-good.
3. O6: all five plane-aware surfaces must run B2 before the first enrollment. The provisioning PR must supply reviewed bindings on all surfaces and pass the new admission validator. W5 adapters/readers, plane-leak zero, wipe coverage and connection budget must be green before the first 1% ramp.
4. Connection budget: with pool sizes 2, each instance adds at most 2 directory + 2 cell connections. Incremental fleet bound = `4 * sum(max instances for the five surfaces)`, plus existing clients. Cell pools open for cell enrollment or wipe. Fleet maxima and database max_connections have not been measured here; N2 must establish headroom or a pooler before 1%.
5. R10/W6: after the cell migration fence, wait CELL_CUTOVER_QUIESCE_SECONDS (65 seconds, strictly greater than the 60-second idle TTL), and drain admitted writers before backfill/flip. The W6 driver is outside this PR. Redis loss disables idle publication and uses authoritative reads; if a write cannot acquire its Redis epoch fence it refuses to commit. A crashed pending writer leaves caching disabled until the operator reconciles that marker against authoritative state; traffic stays authoritative.
6. Rollback before cell serving: routing mode off makes directory rows inert and the cell wipe step a no-op. Ramp zero stops new cell enrollment without moving existing rows. After W5 starts serving cell owners, use its migration ceremony rather than blindly disabling routing.

W5 gates recorded without code changes (flash NB2/NB3/NB6): bind the plane for the lifetime of WebSocket sessions; require auth resolution before relying on plane_for's missing/partial-module fallback; evaluate a short negative cache for rejected uid inputs if metrics justify it. No domain adapter or traffic migration is included here.

Round-2 review dispositions (lead): cell cutovers now reject any explicit generation change (regression added). Recorded W5/W6 gates, no code here: (1) before any route flip (W6), route changes must be observable across workers (route version check, or a verified quiesce longer than both the 300 s process cache and the Redis TTL), with a two-resolver flip test; (2) move `lock_writable_space` after pending-address locks so lock order stays docs then heads (deadlock retries at W5 volume); (3) wipe completeness while routing is rolled back to off (purge sweep at flip-off); (4) retention policy for purge tombstones in `space_heads` (raw uid); (5) the provisioning PR must use literal/env_var bindings or extend the validator's binding grammar; (6) feed pulls for unenrolled spaces return retryable unavailable, not empty; (7) mixed-version serving after the first real cutover write needs fleet-wide B2+ builds.

## Tests

Deterministic regressions interleave stale read → epoch INCR/Firestore commit/idle DEL → refused late cache publication → denied next mutation, for both write seams. Additional tests cover in-flight/crashed writers, Redis outages and key loss, upgrade/generation checks, and quiesce > TTL. Real Postgres tests cover an independent-process stale writer after purge, a resolver paused across the fence, crash-after-tombstone retry, and no implicit enrollment from mutation/cursor/epoch operations. Deployment fixtures cover both environments, all five surfaces, IAM/DSN/ConfigMap bindings, missing bindings, invalid modes, dark manifests, inherited shared-ConfigMap activation, activation from other environment surfaces, and the actual deploy-validator entrypoint.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## New guards (only when adding a check or ratchet)

The PGF B2 round-1 D5 review identified incomplete deployment admission following B1 #24790 and M9 #24778. This extends the existing runtime-env validation primitive with fleet-wide binding admission and positive/negative fixtures; it adds no parallel checker or workflow.

## Merge-owner review fixes

The merge-owner BLOCKING review is addressed by synchronous off-mode checks at all async HTTP/WS routing callsites and before the wipe step (including its heartbeat); a separate `CELL_DIRECTORY_WIPE_ENABLED=false` kill switch; and fail-closed wipe admission requiring an explicit cell route plus the durable cell enrollment head. The retained tombstone admits interrupted-wipe retries, and is written before disabling the directory route so a crash cannot strand that proof. Routing on while the wipe switch is off refuses the required step; this switch must be explicitly enabled after synthetic wipe qualification and before W5 enrollment. Wipe-switch ramp: staging synthetic enrolled owners first, then production cell owners; the W5 integration owner (dazheng) expands before the first W5 enrollment and by 2026-12-06, only while required wipe failures remain zero, both planes are verified empty after deletion, and off-mode added IO remains zero. B2 activates no production cohort.

Route resolution now checks a per-owner Redis epoch on every authenticated hot-path lookup (one GET on a warm cache); Redis loss denies HTTP 503 / WS 1013. Route invalidation publishes a fresh epoch that both process and Redis plane entries must match, including after key loss or an interleaved stale read. This supersedes the earlier deferral of cross-worker route visibility. Flip completion requires successful invalidation plus the existing writer-drain ceremony for already-admitted requests.

The core `apply_cutover_transition` seam itself now rejects `migrated` without persisted cell kind, `cutover_ready`, and a bound destination (completed migrated retries retain idempotence). New regressions cover all async callsites, exact off-mode heartbeat behavior, rejected wipe admission, interrupted-wipe retries, two independent warm resolvers, Redis/key loss, stale cache publication, and direct transition calls. Verification results and exact commands for this round are recorded in `.agent-artifacts/pgf/merge-owner-fix-result.md`.
