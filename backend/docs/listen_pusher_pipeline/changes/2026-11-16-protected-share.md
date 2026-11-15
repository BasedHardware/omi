# Protected lease opportunities for recently finished captures

Source contract: Pipeline accepted Quality's source change in the workspace
quality record `data/run-2026-11-15-quality-12h/pipeline-protected-share-spec.md`.
This is source qualification only; Pipeline review and Release's GPU worker
roll remain required. It does not qualify allowance parking or activate the
provider backlog. R7 and `BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED=false`
remain in force.

See the [scheduler contract](../../listen_pusher_pipeline.mdx#protected-capture-share).

The lease cohort uses the existing immutable `WorkItem.capture_at` plus
`duration_seconds`. Its inclusive window is capture END through END + 7,200 s.
Missing, nonnumeric, nonfinite, nonpositive, future-end or explicitly untrusted
receipt clocks cannot qualify. Enqueue, upload, retry and repair time never
substitute for that clock. No existing row is restamped, and priority, sync
admission and `fresh_capture` merge membership are unchanged.

FRESH retains its existing service and busy-shard fence. Dedicated-batch
workers reserve a default 25% of subsequent lease opportunities for the cohort;
residual slots alternate RECENT and DEEP preference when allocated, then
serve in bounded DRR batches and borrow an empty class's opportunity. The same owner queue deficit and shard duration-service frontier
pay for protected and residual work. Protection changes only which linked job
is the next head; it creates no new priority or queue. Old workers ignore the
cursor metadata, follow valid links, and can drain every job. Shared-live GPU
pulls keep their existing order. During a mixed roll, old workers provide no
protected opportunity guarantee but cannot strand a new class. The CPU serving
factory retains exactly two pool schedulers while protection is enabled, so
small-pull quotas and retry cursors survive maintenance/API calls. Off restores
the original per-call factory. A process restart still resets its hint cursor.

Queries use existing job fields, not a newly written eligibility bit. Ready
selection has at most 16 owner-page lookups and 16 extra claim attempts per
pull, each with LIMIT 8; unique-predecessor queries use LIMIT 2. Thus discovery
reads are at most 16 * (8 + 8 * 2) = 384 per committed set of attempts, plus the
existing control, claim, privacy and policy reads. The query depth does not grow
with the owner's FIFO. A transaction retry can repeat its bounded reads under
the existing contention retry limits (five attempts: at most 1,920 discovery
reads per pull). The metric includes those repeated query reads. The ready cursor lives in the existing
owner/priority queue and rotates past ineligible rows.

Recovery preserves the existing leased-expiry page. Of the normalized retry
limit (maximum 100), the configured percentage goes to a capture-clock page,
and the remainder stays oldest-available-at first. At limit 1, both pages get
one opportunity, so the explicit bound is 2 reads/candidates rather than 1.
Duplicate rows are recovered once. The protected query has exactly one range,
`capture_at` in [now - 14,400, now], ordered descending with `segment_id` as
tie-break. Because admitted duration is at most 7,200 s, this window includes
every valid END within the deadline without scanning the million-row old retry
stock. Due time, the exact END deadline and sticky holds are checked locally;
a second due-time inequality would make LIMIT insufficient to bound index
traversal. The process cursor rotates past future-due rows; a restart resets
the hint without altering custody. A full rotation can take several recovery
cycles and is not a timeliness guarantee.

Known allowance/fair-use holds, sticky last holds, missing authority and privacy
fences cannot receive a protected lease. Authoritative compute admission still
runs in the pump and can refuse a previously unattempted/allowed row; urgency
never grants spending permission. Retry recovery and leasing recheck the
current document, including its clocks. The original allowance parking path is
unchanged.

Four additive Firestore composites (ready/retry, dev/prod) are declared through
`database/batch_pipeline_indexes.py`, included by the index registry and
regenerated into `firestore.indexes.json`. Release must establish READY before
the worker roll. The PostgreSQL Store adapter has matching query/lock semantics
and additive migration `0009_protected_share.sql`; no PostgreSQL primary
cutover or migration execution is included.

Fixed-vocabulary telemetry:

- `omi_batch_pipeline_scheduler_leases_total{service="fresh|protected|recent|deep"}`:
  successful lease opportunities. The recent + deep rate divided by the
  non-fresh service rate measures residual service share.
- `omi_batch_pipeline_protected_cohort_leases_total` and
  `omi_batch_pipeline_protected_cohort_age_seconds`: cohort progress and
  capture-end age at lease, including a cohort job reached through an ordinary
  turn. These are lease signals, not paid compute or delivery receipts.
- `omi_batch_pipeline_protected_discovery_reads{phase="ready|retry"}`:
  per-cycle document-read upper bound (empty query minimum and predecessor
  LIMIT included); excludes existing claim/control/privacy reads, transaction
  billing's separate index-entry charges; includes transaction retries. The single range and
  LIMIT bound each query's traversal independently of old stock.

Rollback: set `BATCH_PIPELINE_PROTECTED_SHARE_ENABLED=off` (also false/0/no).
The default is ON; `BATCH_PIPELINE_PROTECTED_SHARE_PERCENT` defaults to 25,
accepts integers 1–50, and uses 25 for malformed/out-of-range input. Off restores
the old FRESH/RECENT/DEEP selection and original due-retry page, without new
queries, restamps, queue moves or a drain migration. It does not undo leases
already issued. Release owns runtime rollout and readback; this change changes
no serving configuration, capacity, entitlements, held-audio lifetime or provider
backlog controls.

No end-to-end two-hour guarantee is claimed: seal, commit, projection,
composition, policy holds and actual worker capacity require separate outcome
evidence. Validate a new-capture cohort and residual service/read budgets after
one full new-state lookback before attributing any latency improvement.
