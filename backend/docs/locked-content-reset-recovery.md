# Locked-content reset recovery

`LOCKED_CONTENT_RESET_RECOVERY_ENABLED` defaults to `false`. This draft does not
turn it on. No client change, transcription, summarization, usage debit, Stripe
change, or entitlement migration is involved.

The existing quota resolver uses UTC calendar months, independently of Stripe's
billing interval. After authentication, account deletion/cutover fencing and BYOK
validation, ordinary GET/POST/PATCH/PUT HTTP requests can perform one bounded
recovery pass. It admits only successfully resolved ordinary plan allowance
(`plan_within_allowance` or `plan_unlimited`); reviewers, BYOK exemptions, inactive
subscriptions, invalid usage, provider faults and exhausted users cannot authorize
persistent unlocks. Allowance is rechecked between collections.

Each pass reuses the upgrade webhook's unlock helpers, with 100 rows per
collection: legacy memories, canonical memory items, action items, conversations.
The field mask reads document names only. These helpers retain canonical memory
lock-field authority, people-stat invalidation, action-list generation changes and
updated-at stamping. Recovery also sends the upgrade credits invalidation signal
and clears trial-paywall caches. It does not clear rolling fair-use/abuse counters.

Remaining lock fields are the progress checkpoint; no cursor can skip a failed
batch. A token-fenced Redis lease (the existing notification-job release Lua
primitive) coalesces work, with a 60-second retry throttle and a 300-second lease.
Successful empty tails write one durable `completed_period` marker under
`users/{uid}/locked_content_recovery/reset`, and a Redis done key expires at the
next UTC month. Redis eviction costs one state read rather than a new unlock scan.
A full page requires another pass to prove completion. Failures leave the period
incomplete and do not fail authentication; retries also repeat cache invalidation.

On initial enablement, eligible users bootstrap recovery in the current quota
month, restoring the already-locked historical backlog. Subsequent locks in a
completed month remain locked until the next month. This restoration changes
access only, using the existing plan's allowance and no new legacy entitlements.

## Cost and limits

Request-driven recovery avoids scanning inactive accounts or all users on a cron.
Flag off adds no persistence reads. Completed requests pay a Redis get; cold done
cache pays one state read. An active unfinished pass costs one state read, at most
400 lock-document reads and 400 updates, plus three existing allowance lookups
(each finite-plan lookup can scan up to the month's hourly usage rows). Memory
pages are independent, so conservative total-count completion can require an extra
empty pass. Over-cap users retry at most once per minute while making requests;
they incur allowance reads but no content updates. Large backlogs drain over
multiple requests, not necessarily on the first request alone.

The request path runs in FastAPI's synchronous dependency thread. This bounds
row count, not wall time: a slow Firestore/Redis provider can add request latency.
WS-only and inactive accounts wait for an authenticated HTTP request. Concurrent
capture can consume the remaining allowance after the last check; checks are not
transactional with usage writers. Each batch is atomic, but recovery across
collections is resumable rather than atomic, so a parent can become visible before
all child pages drain. Lease expiry may allow overlapping idempotent passes; a
finished request never releases a successor's lease.

## Verification

Hermetic recovery tests cover same-period idempotency, next-month recovery, durable
completion after Redis eviction, bounded draining, partial child failure/resume,
cache-invalidation failure/resume, exhausted/invalid/override denial, allowance
rechecks, lease contention and retry throttling. Helper tests cover actual bounded
legacy/canonical memory updates and bounded conversation updates/cache repair.
Existing upgrade and allowance suites remain relevant because their helpers and
resolver retain the default full-upgrade behavior. No production recovery writes
or client acceptance are performed by this draft.
