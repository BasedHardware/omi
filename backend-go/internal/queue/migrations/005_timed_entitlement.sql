-- Rollback puts unfunded units back on the ordinary timer while retaining their
-- original custody deadline and the generation that refused payment.
ALTER TABLE queue_jobs
    ADD COLUMN timed_generation bigint NOT NULL DEFAULT 0,
    ADD COLUMN timed_deadline timestamptz,
    ADD CHECK ((timed_generation > 0) = (timed_deadline IS NOT NULL)),
    ADD CHECK (timed_deadline IS NULL OR custody_deadline IS NULL);
CREATE INDEX queue_timed_expiry ON queue_jobs(timed_deadline) WHERE timed_deadline IS NOT NULL;
