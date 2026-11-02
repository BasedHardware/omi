# Cleanup capabilities in Dream

Owner decision: 2026-10-14. Dream v2 replaces retrospective cleanup judgment in
this one PR. Schedules below are checked-in declarations, not a live audit.
No production data or production account endpoint was consulted.

## Inventory

Paths are relative to `backend/`, except workflow paths. “FOLD” identifies the
semantic cleanup capability; deterministic intake, delivery, compliance, and
retention subpaths remain with their current authorities.
“No schedule” means absent from `deploy/scheduler/jobs.yaml` and the inspected
workflows; manual deployment and runtime state have not been verified.

| Name / entrypoint | Decision and writes | Dev / prod scheduling; workflow | Gates | Verdict |
| --- | --- | --- | --- | --- |
| Memory maintenance: `modal/memory_maintenance_job.py` → `utils/memory/canonical_short_term_maintenance_cron.py` → `utils/memory/canonical_consolidation.py` | Retired semantic planner/candidate retrieval/retries/cooldown; retrospective merge/retire/supersede now uses Dream verification and journal. | **RETIRED 2026-10-26**: job module, cron coordinator, dev `memory-maintenance-hourly` schedule and both deploy workflows are deleted. The job never served production; required intake moved inline at write time with Dream's sweep as retry/backlog owner (see `dream-agent.md`). | Retired `MEMORY_CANONICAL_MAINTENANCE_ENABLED` and `MEMORY_MAINTENANCE_CAPTURED_AFTER`; runtime-env validation now refuses any reintroduction. | **RETIRED** whole host. Its residual deterministic TTL / canonical-outbox / recurrence-delivery duties have no owner anywhere; tracked as follow-up. |
| Canonical required processing / expiry / outbox: `utils/memory/short_term_promotion.py`, `utils/memory/canonical_required_processing.py` | Normalizes processing state, expiry/retention transitions, dispatches owed required work and delivers committed projection intents. | `canonical_required_processing` stays live: inline intake at write time calls it, Dream retries pending items. `short_term_promotion` retains no prod caller after the cron's retirement and stays only for the e2e lifecycle contract pending follow-up. | Maintenance admission, source/account generations, Flex and delivery bounds. | **KEEP** required processing (inline + Dream retry). Expiry/outbox delivery has no scheduled owner; follow-up tracks where those transitions move. |
| Untitled recovery: `modal/conversation_selfheal_job.py` → `services/conversation_selfheal.py`; `scripts/repair_recovery_dead_letter_untitled.py` | Bounded stale in-progress scan verifies content/jobs, admits SERVER_RECOVERY finalization, terminalizes content-free/protected rows, verifies output and optionally nudges capture wedges. Explicit repair CLI updates qualified dead-letter rows without reprocessing. Writes durable finalization jobs, conversation status/title, CAS scan/verification cursor and notification cooldowns. | No dev/prod schedule or deploy workflow in inspected tree. `docs/omi-core-selfheal-dashboard.md` describes manually provisioning a 15-minute trigger; code is shipped in backend image. Repair CLI is manual. | `SELFHEAL_MODE=off|detect|nudge|heal`, `SELFHEAL_DRY_RUN`, `SELFHEAL_UID_ALLOWLIST`; stale/revision/content/ownership fences. | **KEEP** stranded-pipeline recovery and deterministic terminalization. Dream title/overview repairs cover completed records; they cannot satisfy owed finalization. No independently scheduled completed-record semantic repair job was found. |
| Terminal title prevention: `database/conversation_terminal_title.py`, `utils/conversations/finalizer.py`, `database/conversation_finalization_jobs.py` | Guarantees a kept terminal row gets a deterministic title and cannot be orphaned from its finalization job. Writes terminal conversation fields/receipt. | Request/finalization path, no cron. | Lifecycle/revision/ownership/source fences. | **KEEP** ingest-time prevention. |
| People duplicate cleanup: `utils/agent_capabilities/tools.py:apply_verified_edit(merge_people)`, `database/review_changes.py:merge_review_entities` | Evidenced duplicate identity merge retains redirect and reversible people/node labels/aliases, with ledger and Review journal. | Dream prod hourly sweep (and manual runs); no separate cleanup cron found. | Dream/Review switches, owner eligibility, suppression, current source fences. | **FOLD** verified automatic merge; protected voice/manual/pinned identities remain fenced. No retirement of explicit user tools. |
| False people / speaker attribution: `routers/mcp.py:dismiss_person`, `utils/mcp_server/handlers/other.py`, `database/users.py:dismiss_person`; `database/person_aliases.py` | Explicit user dismissal soft-hides a false profile, with associated read/export visibility rules. Speaker teaching paths update assignments and voice samples. No autonomous people/speaker sweep found. | User API/MCP calls, no schedule. | `people.cleanup` MCP scope; authentication and speaker-teaching ownership/generation fences. | **FOLD** reversible verified `dismiss_person`; **KEEP** user-authorized cleanup and ingest-time teaching. Automatic dismissal soft-hides with a journal and exact Undo; explicit speaker teaching stays protected. |
| Action-item refresh preservation: `utils/conversations/action_item_refresh.py` → `database/action_item_refresh.py` / `action_item_refresh_policy.py` | Reprocessing/merge reconciles tasks by stable identity, preserves completion/user edits, carries donor completion, atomically claims delivery. Writes action items and conversation refresh receipts; refreshes vectors and emits integrations. | Conversation processing and smart-merge refresh, no separate cron. | `ACTION_ITEM_REFRESH_PRESERVE_ENABLED` plus generation/revision/identity fences. | **KEEP** ingest-time prevention and delivery. |
| Action-item dedupe / stale-task cleanup: `utils/conversations/notes_task_context.py`, `database/vector_db.py:find_similar_action_items`, `database/staged_tasks.py`; Dream `close_task` / `retire_task` | Similar-task lookup prevents duplicate creation at ingest/promote. Dream retrospectively closes completed/obsolete tasks through the reversible journal. | Intake and user task calls; Dream prod hourly / manual. No task-dedupe cron found. | Task workflow control/generations, similarity/evidence bounds, Dream/Review policy. | **FOLD** retrospective duplicate/stale judgment; **KEEP** ingest-time dedupe. Duplicate tasks need semantic merge/retirement parity, not deletion. |
| Candidate integration retry: `utils/task_intelligence/candidate_integration_sweeper.py`, `routers/candidate_integration_sweep.py` | Retries already accepted task integration delivery; updates integration receipts/attempts. | Prod `candidate-integration-sweep`, every 15 min; intentionally no dev declaration because dev shares data plane. | Delivery state, claim leases, account generations, integration auth. | **KEEP** deterministic delivery of user-approved work. |
| Smart merge audit: `database/smart_merge_audit.py`, `utils/conversations/smart_merge_audit.py` | Content-free sibling audit inside ingest absorb; post-delete survivor-age metric. Does not decide merge/repair outcomes. Writes audit ids/enums/counts with `expire_at`; emits counters. | Ingest absorb / user deletion paths, no cron. Audit TTL is documented as not activated. | `CONVERSATION_SMART_MERGE_AUDIT_ENABLED`; deletion/gate fences; smart merge mode. | **KEEP** ingest-time audit/prevention evidence. A future semantic false-merge review can be a Dream capability; no existing audit job to retire. |
| Smart merge cleanup / refresh: `utils/conversations/smart_merge.py` | Deterministically pays donor cleanup/audio movement, ancestry flattening and survivor refresh owed by a committed absorb. Writes donor tombstones/redirects and refresh revisions. | Finalization/intake path, no independent schedule. | Smart-merge mode, source/revision/live-ownership/refresh leases. | **KEEP** completion of an ingest mutation. Dream must not reinterpret a committed merge as permission to delete. |
| Frame requests: `modal/frame_request_retention_job.py` → `services/frame_request_retention.py`, `database/frame_requests.py` | Expires pending requests, removes expired metadata/output and orphan storage objects, resumes deletion retries under a rotating lease. | Dev and prod `frame-request-retention-hourly`, hourly **planned** declarations; `.github/workflows/gcp_frame_request_retention_job.yml` manual deploy. The retired maintenance host's legacy fallback pass is deleted with the host; this job is the only retention owner. | Retention TTL/device policy, per-page bounds, lease/generation. | **KEEP** deterministic retention/compliance. |
| X connector incremental sync: `modal/x_connector_sync_job.py` → `utils/x_connector.py` / `utils/llm/connector_synthesis.py` | Fetches new authorized X data, refreshes OAuth tokens/cursors, writes X posts and connector-synthesized reusable facts/profile context. It is ingestion, not a cleanup sweep. | Not in scheduler manifest. `.github/workflows/gcp_x_connector_sync_job.yml` manually deploys and validates existing `x-connector-sync-6h`; runbook describes six-hour cadence. Missing scheduler requires explicit first-deploy input; live presence unverified. | OAuth configured gate (`X_OAUTH_CLIENT_ID`, `X_OAUTH_CLIENT_SECRET`, `X_OAUTH_REDIRECT_URI`, `X_OAUTH_SCOPES`), user connection/token state and synthesis admission. | **KEEP** authorized ingestion. Dream may judge the resulting facts through memory hygiene. |
| Notification / memory check: `modal/job.py` → `utils/notifications.py` | Local-hour summaries/reminders/pushes; read-only Redis memory diagnostics. Writes delivery state, not canonical cleanup. | Prod `notifications-job-scheduler-trigger`, every 15 min; `.github/workflows/gcp_notifications_job.yml`. No dev declaration. | Notification preferences/local hour, delivery lock; memory flags are no longer deploy bindings. | **KEEP** delivery/diagnostics. |
| Automatic Chat materialization + weekly memory decision review | Retired from notifications host; no active caller or schedule in that host. | No active notification cron invocation; backend guide documents retirement. | Removed host bindings, not a flag to resurrect. | **ALREADY DEAD**; do not migrate dead work. |
| Account/conversation/privacy wipes: `routers/users.py`, `services/users/`, `database/legal_holds.py`, `database/memory_apply_store.py` tombstone boundaries | User-authorized deletion, retention/legal holds, source/account-generation invalidation and canonical anti-resurrection receipts; deletes/scrubs content and derived artifacts. | Account-deletion Cloud Tasks; finalization/user deletion paths. Explicit repair/reconcile tools do not become Dream tools. | Auth/OIDC, legal holds, durable deletion markers, generation fences. | **KEEP** deterministic compliance/deletion. |
| Sync backfill sequencing and queue repair: `database/sync_backfill_sequencer.py`, `utils/sync/`, `database/sync_jobs.py` | Releases eligible queued backfills and retries owed sync/finalization/audio work without re-deciding user facts. Writes job leases/status/receipts. | Prod `sync-backfill-uid-sequencer` every 2 min; dev paused. Finalization/audio Cloud Tasks are event-driven. | Queue/source/account generation, leases, ingest budgets. | **KEEP** deterministic ingestion recovery. |
| Vector/graph projection repair: `scripts/vector_repair_outbox_worker_entrypoint.py`, memory outbox delivery, `scripts/backfill_*vectors.py`, `scripts/firestore_read_reconcile.py` | Reconciles indexes/projections from canonical source; writes indexes, delivery receipts and infrastructure artifacts. | Explicit worker/operator paths; Firestore reconciliation workflow has a schedule. No semantic cleanup cron. | Current source/control watermark, leases, deployment/query readiness, explicit operator bounds. | **KEEP** deterministic projection/infrastructure repair. |
| Remaining operator backfills / reconciliation: `scripts/backfill_*.py`, `scripts/repair_memory_state_head.py`, `scripts/billing_reconcile.py`, `scripts/finops/`, storage lifecycle workflow | Bounded migration/repair of source metadata, schema, billing/state-head/index/retention contracts; no open-ended autonomous memory judgment. | Operator CLI or named infrastructure/billing workflows; not Dream's schedule. | Explicit operator flags, generation/source checks and domain-specific authority. | **KEEP** migrations, billing and deterministic repair. |

## Retirement and preserved authorities

`canonical_consolidation.py` no longer contains a model planner, candidate search,
semantic batch output, semantic attempt/quarantine state, or semantic watermark.
The maintenance host's dreaming state, 20-hour cooldown, overflow policy and
duplicate Dream drain are removed. `MEMORY_CANONICAL_CONSOLIDATION_ENABLED`, its
batch/candidate tuning reads, and `MEMORY_CANONICAL_MAINTENANCE_FLEX` disappear from
runtime bindings and the feature registry. Old stored control fields/receipts are
retained as history; nothing silently migrates or rewrites them.

The 2026-10-18 flag review removed the dev daily memory sweep schedule and its
two deployment workflows, plus the knowledge-ledger drain job. Stored ledger
and sweep records remain in place for existing export, deletion, and retention
handling. The 2026-10-26 retirement deleted `memory-maintenance-hourly`, its
manifest entry and both deploy workflows (`gcp_memory_maintenance_job.yml`,
`gcp_memory_maintenance_job_auto_dev.yml`); the job module and cron coordinator
are gone and runtime-env validation refuses their reintroduction. Independent
frame retention and delivery jobs remain.

## Dream policy

One shared shaped-agent session hunts with six bounded tools. Two independent
reserved-lane verifier responses must both agree before an eligible, non-demoted
kind applies. Split or demoted proposals use ranked Review attention; both
disagree drops the edit. Low-value questions never consume attention. The
kill switch, lease, source/generation fences, suppression and journal/Undo apply
to every autonomous mutation. The former sampled-majority and context modes are
deleted. All-user rollout is configured by `DREAM_AGENT_ELIGIBILITY=all` in prod.

Automatic kinds are spelling, title, overview, vocabulary, merge/retire/supersede
memory, dismiss/merge people, merge/retire tasks, duplicate-conversation hiding
with link, and language correction. No kind hard-deletes source records. Captured
speech remains immutable; spelling uses an encrypted correction overlay.

## Parity checks

The retained disposition tests cover canonical head/item/graph/outbox atomicity,
source generation and idempotent retry. Required-intake tests cover valid receipts,
ordinary-observation fairness, bounded capture/id query/cursor wrapping, failures
and concurrent cursor protection. Maintenance tests cover prior privacy outboxes
before malformed rows, newly committed delivery, all-account delivery and resource
deferral without skipping a UID. Existing daily-sweep, finalization, task-refresh,
smart-merge and compliance tests remain authoritative for their own pipelines.

Dream's synthetic replay and cleanup tests cover retrospective judgments and
reversals. Local evidence does not establish deployed Scheduler state, real model
accuracy or provider billing. See [Dream architecture](dream-agent.md) for budgets,
operator dry-run, canary, metrics and rollback.
