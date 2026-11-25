-- Positive generations come from the entitlement authority. Keep the funded generation
-- too, so a delayed exhaustion observation cannot recreate a released hold.
ALTER TABLE queue_tenants
    ADD COLUMN entitlement_generation bigint NOT NULL DEFAULT 0,
    ADD COLUMN entitlement_check_at timestamptz;
CREATE INDEX queue_entitlement_checks ON queue_tenants (entitlement_check_at)
    WHERE entitlement_check_at IS NOT NULL;

-- A held row has neither a due time nor an active lane key. This keeps older
-- dispatchers from selecting it or letting it block the head of its lane.
ALTER TABLE queue_jobs
    ADD COLUMN owed_since timestamptz,
    ADD COLUMN custody_deadline timestamptz,
    ADD COLUMN held_order_key text COLLATE "C",
    ADD COLUMN audio_seconds double precision NOT NULL DEFAULT 0,
    DROP CONSTRAINT queue_jobs_check,
    ADD CHECK ((outcome IS NULL AND custody_deadline IS NULL) = (ready_at IS NOT NULL)),
    ADD CHECK (custody_deadline IS NULL OR
        (state='waiting' AND outcome IS NULL AND order_key IS NULL AND NOT lane_head)),
    DROP CONSTRAINT queue_jobs_outcome_check,
    ADD CHECK (outcome IN ('success','failure','fenced','expired_unfunded')),
    DROP CONSTRAINT queue_jobs_check1,
    ADD CHECK (CASE state
        WHEN 'completed' THEN outcome IN ('success','fenced','expired_unfunded')
        WHEN 'parked' THEN outcome IS NULL OR outcome='failure'
        ELSE outcome IS NULL END);
CREATE INDEX queue_held_owner ON queue_jobs (uid) WHERE custody_deadline IS NOT NULL;
CREATE INDEX queue_held_expiry ON queue_jobs (custody_deadline) WHERE custody_deadline IS NOT NULL;
CREATE INDEX queue_committed_order ON queue_jobs
    (uid,kind,order_key,order_at,order_sub_us,order_sort,job_key)
    WHERE order_key IS NOT NULL AND outcome='success';
-- Anonymous lifetime count survives normal tenant erasure.
ALTER TABLE queue_settings ADD COLUMN expired_unfunded bigint NOT NULL DEFAULT 0;
