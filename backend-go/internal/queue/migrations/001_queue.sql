CREATE TABLE queue_tenants (
    uid text PRIMARY KEY,
    last_claim timestamptz NOT NULL DEFAULT '-infinity',
    check_after timestamptz NOT NULL DEFAULT '-infinity'
);
CREATE INDEX queue_tenants_turn ON queue_tenants (last_claim, uid);

-- A lane belongs to one tenant: two tenants using the same kind and order key never share one.
CREATE TABLE queue_lanes (
    uid text NOT NULL REFERENCES queue_tenants ON DELETE CASCADE,
    kind text NOT NULL,
    order_key text COLLATE "C" NOT NULL,
    PRIMARY KEY (uid, kind, order_key)
);

CREATE TABLE queue_settings (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    erasure_salt bytea NOT NULL DEFAULT uuid_send(gen_random_uuid())
);
INSERT INTO queue_settings DEFAULT VALUES;

CREATE TABLE queue_erasure (
    tenant_hash bytea PRIMARY KEY,
    completed boolean NOT NULL DEFAULT false
);

CREATE SEQUENCE queue_lease_token;
CREATE TABLE queue_jobs (
    job_key text COLLATE "C" PRIMARY KEY,
    uid text NOT NULL REFERENCES queue_tenants ON DELETE CASCADE,
    kind text NOT NULL,
    -- The version of meta and checkpoint. A replica claims only the formats it declares.
    format integer NOT NULL CHECK (format >= 1),
    subject text NOT NULL,
    meta jsonb NOT NULL,
    checkpoint jsonb NOT NULL DEFAULT 'null',
    budget_allowed boolean NOT NULL DEFAULT false,
    gated boolean NOT NULL DEFAULT false,
    initializing boolean NOT NULL DEFAULT false,
    order_key text COLLATE "C",
    order_at timestamptz NOT NULL,
    order_sub_us smallint NOT NULL,
    order_sort text COLLATE "C" NOT NULL,
    lane_head boolean NOT NULL DEFAULT false,
    state text NOT NULL CHECK (state IN ('ready','leased','waiting','blocked','parked','completed')),
    step text NOT NULL,
    ready_at timestamptz,
    lease_until timestamptz,
    run_at timestamptz NOT NULL,
    blocked_since timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    deterministic_attempts integer NOT NULL DEFAULT 0 CHECK (deterministic_attempts >= 0),
    reconcile_attempts integer NOT NULL DEFAULT 0 CHECK (reconcile_attempts >= 0),
    budget_requeues integer NOT NULL DEFAULT 0 CHECK (budget_requeues >= 0),
    lease_token bigint NOT NULL DEFAULT 0,
    reason text,
    outcome text CHECK (outcome IN ('success','failure','fenced')),
    intent text,
    intent_transient boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    -- A terminal row has an outcome and no timer; every other row has a timer and no outcome.
    CHECK ((outcome IS NULL) = (ready_at IS NOT NULL)),
    -- completed means success or fenced. parked means a failure, or (with no outcome yet) the
    -- wait before the single budget requeue. No other state carries an outcome.
    CHECK (CASE state
        WHEN 'completed' THEN outcome IN ('success','fenced')
        WHEN 'parked' THEN outcome IS NULL OR outcome = 'failure'
        ELSE outcome IS NULL END),
    CHECK (state <> 'leased' OR (lease_token > 0 AND lease_until IS NOT NULL)),
    CHECK (NOT lane_head OR order_key IS NOT NULL),
    -- A gated job is resumed by key, which would bypass lane order: the two do not combine.
    CHECK (NOT (gated AND order_key IS NOT NULL))
);

CREATE INDEX queue_jobs_due ON queue_jobs (uid, ready_at, job_key)
    WHERE ready_at IS NOT NULL;
CREATE INDEX queue_jobs_unordered_due ON queue_jobs (uid, ready_at, job_key)
    WHERE ready_at IS NOT NULL AND (order_key IS NULL OR state = 'parked');
CREATE INDEX queue_jobs_subject ON queue_jobs (uid, kind, subject)
    WHERE outcome IS NULL;
CREATE INDEX queue_jobs_order ON queue_jobs (uid, kind, order_key, order_at, order_sub_us, order_sort, job_key)
    WHERE order_key IS NOT NULL AND state NOT IN ('parked','completed');
CREATE UNIQUE INDEX queue_jobs_head ON queue_jobs (uid, kind, order_key) WHERE lane_head;
CREATE INDEX queue_jobs_parked ON queue_jobs (uid, created_at, job_key) WHERE state = 'parked';
-- The schedule watcher sleeps until the earliest due time across all tenants.
CREATE INDEX queue_jobs_next_due ON queue_jobs (ready_at) WHERE ready_at IS NOT NULL;

-- Each command in the volatile function uses a fresh READ COMMITTED snapshot.
-- Check the lease after acquiring both session locks, especially if erase
-- committed while the first lock was waiting. The caller releases both locks.
CREATE FUNCTION queue_acquire_guard(tenant text, job text, token bigint)
RETURNS boolean
LANGUAGE plpgsql VOLATILE
AS $$
BEGIN
    PERFORM pg_advisory_lock_shared(hashtextextended(tenant,447119));
    PERFORM pg_advisory_lock(hashtextextended(job,447120));
    RETURN EXISTS (
        SELECT 1 FROM queue_jobs
        WHERE job_key=job AND uid=tenant AND lease_token=token
          AND state='leased' AND lease_until > clock_timestamp()
    );
END;
$$;
