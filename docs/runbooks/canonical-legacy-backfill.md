# Canonical legacy memory backfill (single user)

**Purpose:** Migrate a whitelisted user's active legacy `memories` rows into canonical `memory_items` without mutating or deleting legacy data.

For first-user dogfood, start with the **bucketed** inventory. The `stage-all-for-admission` strategy is also safe: it copies active rows only into Short-term quarantine. Manual and positively reviewed rows require processing; all other rows remain hidden `pending_admission` candidates.

**Library:** `utils.memory.legacy_backfill.backfill_user_bucketed`
**CLI:** `backend/scripts/backfill_legacy_memories.py`
**Rollout controls:** [`canonical-memory-rollout-flags.md`](canonical-memory-rollout-flags.md)

## Safety contract

- **Read-only on legacy** — uses `get_non_filtered_memories` only; never calls legacy mutators.
- **Write-only on canonical** — applies via `apply_long_term_patch_firestore`; obvious noise and sensitive rows never enter canonical staging.
- **Cohort gate** — backfill runs only when `uid` is in `CANONICAL_MEMORY_USERS` (or `--allow-admin-override`).
- **Idempotent** — backfill ids are `mem_` + hash(`uid`, `legacy_memory_id`); apply path honors `idempotency_key`.
- **Both-store dedup** — if live extraction already wrote the same fact (`extraction_memory_id` from `conversation_id` + `content`), backfill skips that row.
- **Bucketed dogfood** — bucketed runs preserve legacy timestamps, stage only manual or positively reviewed rows for required processing, and hold unreviewed profile/noisy/sensitive rows out of durable memory.
- **Reversible** — remove `uid` from `CANONICAL_MEMORY_USERS` and redeploy to return them to legacy reads; legacy rows remain intact.

## Bulk automation

Use `scripts/bulk_backfill_legacy_memories.py` for governed inventory and
write-only enrollment/staging across an explicit UID list. The command defaults
to dry-run and emits only counts, bucket totals, and character/token proxies. It
never returns memory text or bucket samples.

The bulk worker stores its server-owned checkpoint at
`users/{uid}/memory_control/legacy_canonical_backfill`. States progress through
`not_started`, `inventory_done`, `enrolled`, `processing`, `staged`, and
`read_ready`; a governor or operator pause uses `paused`, while isolated failures
use `failed`. Re-entry is idempotent. A capped run resumes from the existing
single-user apply checkpoint, and a failed run restarts deterministic staging so
successful rows are skipped and failed rows can be retried.

`read_ready` means enrollment and staging reconciled for that UID. It does not
change `MEMORY_MODE`, add the UID to `CANONICAL_MEMORY_USERS`, grant default
memory reads, or open the global read gate. Those remain explicit later rollout
actions.

For a code-whitelisted user on an enabled maintenance deployment, the scheduler
owns the same bounded progression: it creates only the known inert onboarding
state, advances only that exact state to write, and invokes this checkpointed
page. At terminal staging it reconciles only a scheduler-owned write control to
the trusted state-head generation and permits graph enrichment for that user.
Existing write/read controls are preserved; malformed or manually altered
controls fail closed. The scheduler does not perform the later read cutover.

### 1. Prepare an explicit UID file

Use either repeatable `--uid` flags or a UTF-8 newline-delimited/JSON UID file:

```text
# cohort-uids.txt
uid-canary-a
uid-canary-b
```

Do not put email addresses, names, or memory content in this file. The bulk
command does not query all users or silently expand the cohort.

### 2. Inventory dry-run

Point `--firestore-project` at the data-plane project. For local testing, start
the Firestore emulator, export `FIRESTORE_EMULATOR_HOST`, and use a disposable
project name with seeded fake users.

```bash
cd backend
python scripts/bulk_backfill_legacy_memories.py \
  --uid-file cohort-uids.txt \
  --firestore-project based-hardware \
  --max-users-per-run 10 \
  --max-admitted-rows-per-user 100 \
  --max-estimated-tokens-per-run 100000 \
  --concurrency-limit 1
```

Review `source_count`, `bucket_counts`, `admitted_candidate_count`, and
`admitted_candidate_estimated_tokens`. `actions` contains would-be enrollment
and staging operations. Dry-run writes no enrollment or migration checkpoint
documents.

### 3. Canary apply

Start with one UID and conservative caps. Apply mode requires both a fixed
confirmation phrase and the exact deduplicated input count. A UID outside the
code-owned cohort additionally requires both admin-override flags; the command
prints a cohort patch suggestion but never edits the cohort.

```bash
python scripts/bulk_backfill_legacy_memories.py \
  --uid uid-canary-a \
  --firestore-project based-hardware \
  --apply \
  --confirm-apply bulk-canonical-memory-backfill \
  --confirm-user-count 1 \
  --allow-admin-override \
  --i-understand-uids-not-whitelisted \
  --max-users-per-run 1 \
  --max-admitted-rows-per-user 25 \
  --max-estimated-tokens-per-run 25000 \
  --wall-clock-seconds 600 \
  --concurrency-limit 1
```

If existing enrollment documents differ, inspect them first and rerun only with
`--allow-existing-update` after confirming the requested write-stage payload.
The worker always enrolls at `stage=write`; it has no read-stage flag.
Bulk enrollment writes only the per-user `memory_control/state` document. It
does not rewrite rollout-wide global read or write-convergence gates and does
not fabricate `memory_state/head` or compatibility projection data.

The default `stage-all-for-admission` path is Firestore-only. Optional reviewed
bucket upgrades remain capped by the same per-user row budget:

```bash
python scripts/bulk_backfill_legacy_memories.py \
  --uid uid-canary-a \
  --firestore-project based-hardware \
  --apply \
  --confirm-apply bulk-canonical-memory-backfill \
  --confirm-user-count 1 \
  --allow-admin-override \
  --i-understand-uids-not-whitelisted \
  --process-bucket manual_required_promotion \
  --max-users-per-run 1 \
  --max-admitted-rows-per-user 25 \
  --max-estimated-tokens-per-run 25000
```

This CLI does not invoke an LLM. Required `memory_l2` processing and promotion
remain exclusively owned by `memory-maintenance-job`, which processes admitted
rows under its own bounds. Never run L2 over `pending_admission`,
`hold_noise`, or `hold_sensitive` rows.

### Pause and resume

Set `MEMORY_BULK_BACKFILL_PAUSED=true` on the maintenance shell for an immediate
local pause, or set the server-owned Firestore document
`memory_control/legacy_canonical_backfill_pause` to `{"paused": true}`. The
worker checks pause before inventory and again before each enrollment/staging
boundary. A pause-control read error fails closed.

Clear the pause flag and rerun the exact command to resume. Do not delete or
manually advance checkpoint documents. Row, token, user, and wall-clock limits
stop cleanly; increase a cap only after reviewing the prior structured summary.

### Rollback

Before a read flip, rollback is simply: pause bulk work and do not add the UID to
the code-owned cohort. If a later rollout already selected the UID, remove it
from `backend/config/canonical_memory_cohort.py` and redeploy through the normal
reviewed path. Canonical staged rows and checkpoints remain for idempotent
resume; legacy memories remain untouched and must not be deleted or rewritten.

## Single-user preconditions

1. **Target uid chosen** — use this section for one-off dogfood; use the governed bulk command above for cohorts.
2. **Backend env** — `GOOGLE_APPLICATION_CREDENTIALS` (or emulator) points at the intended project.
3. **Product entitlement** — confirm the uid is in `CANONICAL_MEMORY_USERS` in
   `backend/config/canonical_memory_cohort.py` before a normal apply:
   ```python
   CANONICAL_MEMORY_USERS: frozenset[str] = frozenset({
       "your-firebase-uid",
   })
   ```
   For a new enrollment, do not deploy this product-path selector merely to get
   a dry-run. Use the CLI's explicit one-user admin-override ceremony for
   staging, then coordinate entitlement deployment with persisted readiness and
   maintenance as described in the rollout-controls runbook.
4. **Runtime cohort** — add the same uid to `MEMORY_ENABLED_USERS` only in the
   intended environment. This readiness fence does not replace the code-owned
   product entitlement.
5. **Control state** — `users/{uid}/memory_control/state` is created automatically on first real run (dry-run does not create it).

## Procedure

### 1. Bucket inventory dry run (no writes)

```bash
cd backend
python scripts/backfill_legacy_memories.py --uid YOUR_UID --strategy bucketed --dry-run
```

Expect:

- `dry_run: true`
- `source_count` = active legacy rows with non-empty content
- `bucket_counts` = full inventory by bucket
- `bucket_samples` = small row samples for review
- `written_count: 0`
- `cohort_gated: false` (if gated, add uid to whitelist first)

Buckets:

| Bucket | Writes? | Destination | Intended use |
|--------|---------|-------------|--------------|
| `manual_required_promotion` | Yes | pending `short_term` with `promotion.required=true` | User/manual memories that must be normalized before promotion |
| `profile_required_promotion` | No | None in bucketed mode; `pending_admission` under stage-all | Unreviewed profile-like rows requiring a separate admission decision |
| `reviewed_long_term` | Yes | pending `short_term` with `promotion.required=true` | Positively reviewed rows that must still be normalized before promotion |
| `archive_review` | No | None | Non-obvious rows for later manual/archive policy review |
| `hold_noise` | No | None | Downloads/file/project inventories, focused-app or attention telemetry, raw email bodies, test markers, imperative fragments, empty/low-signal rows |
| `hold_sensitive` | No | None | Credential/token/password/secret-like rows |

### 2. Bucket dry run (no writes)

Dry-run the first bucket before writing it:

```bash
python scripts/backfill_legacy_memories.py --uid YOUR_UID --strategy bucketed --bucket manual_required_promotion --dry-run
```

Expect `intended_count` to match the reviewed bucket size minus existing canonical destinations.

### 3. Apply one bucket

Apply only after reviewing the bucket inventory and samples:

```bash
python scripts/backfill_legacy_memories.py --uid YOUR_UID --strategy bucketed --bucket manual_required_promotion
```

Repeat bucket dry-run, review, and apply for the next approved writable bucket. Do not apply hold buckets; the script reports them as non-writable.

Monitor JSON output after each applied bucket:

| Field | Success signal |
|-------|----------------|
| `completed` | `true` |
| `verified` | `true` for the selected bucket |
| `selected_bucket` | The bucket you intended to apply |
| `written_count` + `skipped_*` | Should account for the selected bucket rows |
| `vector_sync_failures` | `0` |
| `errors` | `[]` |

Re-run is safe: already-present and both-store-duplicate rows are skipped. Stage-all reports `admissible_count` and `skipped_non_admissible` so source inventory is not confused with rows allowed into canonical staging.

## Historical remediation plan (read-only)

Rows written by older backfill versions may already be active Long-term. Do
**not** rerun backfill to clean them: deterministic ids make that a no-op, and
normal backfill intentionally does not mutate projections or legacy KG state
directly. Build a metadata-only plan first:

```bash
cd backend
python scripts/plan_legacy_backfill_remediation.py --uid YOUR_UID
```

The planner scopes itself to active canonical rows with explicit `legacy_backfill` provenance. It returns `keep`, `review`, and `archive` recommendations without returning raw content or changing Firestore, vectors, keyword indexes, or the knowledge graph. It intentionally excludes unattributed historical Long-term rows until their ingress lineage has been audited.

### 4. Verification queries

**Firestore (console or script):**

- Legacy unchanged: `users/{uid}/memories/*` — same doc count as before; no `invalid_at` changes from backfill.
- Canonical items: `users/{uid}/memory_items/*` — one active Short-term submission per applied writable-bucket row (either backfill id or live-write id).
- Required-processing rows: selected `manual_required_promotion` / `reviewed_long_term` rows are `tier=short_term`, `processing_state=pending`, have `promotion.required=true`, `promotion.processing_status=pending_processing`, source/content provenance, old `captured_at`, and future `expires_at`.
- Quarantined rows: stage-all unreviewed rows have `promotion.required=false` and `promotion.processing_status=pending_admission`; they are hidden from agent/search/KG reads and do not enter the required processor.
- Control state: `users/{uid}/memory_control/state` exists after a real run.

**Python reconcile (same logic as the library):**

```python
from utils.memory.legacy_backfill import backfill_user_bucketed

report = backfill_user_bucketed("YOUR_UID", bucket="manual_required_promotion", dry_run=True)
assert report.errors == []
```

**Read path smoke:** with uid still whitelisted, `GET /v3/memories` may show required pending rows as Short-term. Agent/developer/MCP/search reads must not return pending text.

## Rollback (kill-switch)

1. Remove the uid from `CANONICAL_MEMORY_USERS` in
   `backend/config/canonical_memory_cohort.py` and redeploy.
2. User immediately reads legacy `memories` again.
3. Canonical `memory_items` written during backfill are **not** deleted and **not** copied back to legacy — accepted staleness per rollout policy.
4. Re-whitelisting resumes canonical reads; backfill re-run is idempotent.

## When *not* to proceed

- `cohort_gated: true` — fix whitelist before real run.
- `verified: false` after a completed bucket run — inspect `discrepancy` and missing selected-bucket items.
- `errors` non-empty — fix root cause; re-run the same bucket. Bucketed writes are deterministic and idempotent.

## Operational notes

- **Provenance:** bucketed rows preserve legacy `created_at` as `captured_at` and legacy `updated_at` as `updated_at`. Short-term bucketed rows set `expires_at` to migration time + 30 days so promotion can process them.
- **Stage-all checkpoint:** `backfill_user` and `--strategy stage-all-for-admission` use the legacy id-set checkpoint. Bucketed dogfood does not use that checkpoint; re-runs reconcile by deterministic canonical ids and can upgrade an existing candidate after positive review.
- **Derived stores:** pending backfill rows create no keyword, vector, or KG projection. Those projections are built only after processing and Long-term promotion.

## Canonical maintenance projection outbox

Scheduled maintenance (`canonical_short_term_maintenance_cron`) deterministically selects a server-bounded set of eligible pending Short-term items, routes every selected item through consolidation, then drains the durable normal outbox that converges compatibility and vector projections. Overflow remains immediately eligible on the next Scheduler run; there is no 24-hour watermark delay. The authoritative Firestore mutation and its outbox event commit together; provider delivery is never part of the admission transaction.

The datastore applies eligibility before each query cap: required processing selects active pending required rows (negative review is terminal `processing_rejected`), TTL selects active processed expired rows by `expires_at, memory_id`, and consolidation selects active processed source-active rows by `captured_at, memory_id`. If an eligible row is absent from one bounded result, unrelated or terminal rows cannot keep it hidden from later passes.

After a per-user maintenance run, inspect `outbox.delivered_count`, `outbox.retryable_failure_count`, `outbox.dead_letter_count`, `outbox.ack_failed_count`, and `outbox.errors`. The cohort cron aggregates the same outcomes as `outbox_delivered_total`, `outbox_retryable_failures_total`, `outbox_dead_letters_total`, and `outbox_ack_failures_total`; any delivery failure also makes `errors` non-empty so the Cloud Run Job fails visibly.

A retryable failure remains in `users/{uid}/memory_outbox` with a bounded `available_at` backoff and is retried by the next enabled maintenance run. A dead letter, acknowledgement failure, or worker error requires inspecting the outbox document's sanitized `status` and `last_error_code`, repairing the provider or lease failure, and following the outbox recovery procedure. Do not rerun the retired generic promotion path or issue a targeted vector upsert: the canonical item plus durable outbox event remain the repair authority.
