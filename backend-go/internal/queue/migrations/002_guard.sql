-- Each command in the volatile function uses a fresh READ COMMITTED snapshot.
-- Check the lease after acquiring both session locks, especially if erase
-- committed while the first lock was waiting. The caller releases both locks.
CREATE OR REPLACE FUNCTION queue_acquire_guard(tenant text, job text, token bigint)
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
