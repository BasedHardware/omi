-- Expand-only: durable custody deferral episode state for PL-342 (#24556).
ALTER TABLE outbox ADD COLUMN deferred_reason text;
ALTER TABLE outbox ADD COLUMN deferred_since float8;
