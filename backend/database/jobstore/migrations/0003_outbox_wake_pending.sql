-- The outbox owns wake creation (lead ruling 10-19): a minted wake token is "pending" until the task
-- create succeeded, so a failed create is found by sweep instead of being forgotten.
ALTER TABLE outbox ADD COLUMN wake_pending boolean NOT NULL DEFAULT true;
CREATE INDEX outbox_wake_pending ON outbox (namespace, kind, id) WHERE done_at IS NULL AND wake_pending;
