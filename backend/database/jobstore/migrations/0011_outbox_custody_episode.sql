-- PL-342: a callback custody deferral keeps its episode across claims, like the Firestore outbox's
-- `deferred_reason` / `deferred_since`. A cause that has deferred the row for the whole grace polls hourly
-- instead of at the requested cadence. A closed row never reopens (a new obligation is a new row), so
-- `created_at` bounds the episode and no old age is inherited.
ALTER TABLE outbox ADD COLUMN deferred_reason text;
ALTER TABLE outbox ADD COLUMN deferred_since float8;
