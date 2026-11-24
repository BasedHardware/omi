package queue

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
	"github.com/BasedHardware/omi/backend-go/internal/queue/rules"
)

// inSupported completes the SQL test that a job is one this replica declared it can run:
// "(x.kind,x.format)" + inSupported. $1 and $2 are the parallel kind and format arrays of
// the claim's supported set.
const inSupported = ` IN (SELECT k,f FROM unnest($1::text[],$2::int[]) AS s(k,f))`

// candidate picks the next job fairly: the tenant that was served longest ago, then that
// tenant's earliest due job. An ordered lane offers only its current head (or, with no head,
// its first member in lane order), so a lane never runs two jobs at once. SKIP LOCKED lets
// replicas dispatch concurrently without waiting on each other.
//
// Only jobs whose kind and format this replica declared are offered, and the test is made
// before a job is chosen or locked. A lane whose head this replica cannot run is skipped
// whole: the head is picked first and tested second, so its successors stay behind it.
const candidate = `
 SELECT ` + columns + ` FROM queue_tenants t
 CROSS JOIN LATERAL (
   SELECT ` + rawColumns + `
   FROM (
     (SELECT u.job_key,u.ready_at FROM queue_jobs u
       WHERE u.uid=t.uid AND u.ready_at <= statement_timestamp()
         AND (u.order_key IS NULL OR u.state='parked') AND (u.kind,u.format)` + inSupported + `
       ORDER BY u.ready_at,u.job_key LIMIT 1)
     UNION ALL
     (SELECT o.job_key,o.ready_at FROM queue_lanes l
       JOIN queue_jobs o ON o.job_key=COALESCE(
         (SELECT h.job_key FROM queue_jobs h
           WHERE h.uid=l.uid AND h.kind=l.kind AND h.order_key=l.order_key AND h.lane_head),
         (SELECT p.job_key FROM queue_jobs p
           WHERE p.uid=l.uid AND p.kind=l.kind AND p.order_key=l.order_key
             AND p.state NOT IN ('parked','completed')
           ORDER BY p.order_at,p.order_sub_us,p.order_sort,p.job_key LIMIT 1)
       )
       WHERE l.uid=t.uid AND l.kind=ANY($1) AND o.ready_at <= statement_timestamp()
         AND (o.kind,o.format)` + inSupported + `
       ORDER BY o.ready_at,o.job_key LIMIT 1)
   ) available JOIN queue_jobs q USING (job_key)
   WHERE q.ready_at <= statement_timestamp()
   ORDER BY available.ready_at,available.job_key LIMIT 1 FOR UPDATE OF q SKIP LOCKED
 ) j
 WHERE t.check_after<=statement_timestamp() AND EXISTS (
   SELECT 1 FROM queue_jobs d WHERE d.uid=t.uid AND d.ready_at<=statement_timestamp() AND d.kind=ANY($1)
 )
 ORDER BY t.last_claim,t.uid LIMIT 1 FOR UPDATE OF t SKIP LOCKED`

// direct selects one job by key for a resume, with whether its gate wait has run out. The
// database's clock decides that, in the same statement that locks the row, so a resume can
// never win after the timeout just because the watcher has not reached the row yet.
const direct = "SELECT " + columns + `,COALESCE(j.ready_at <= clock_timestamp(),false)
 FROM queue_jobs j WHERE j.job_key=$1 FOR UPDATE OF j`

// tryClaimLocks takes the tenant lock before the job lock and never waits: a claim must
// not hold row locks while an erase or an earlier lease's last guarded call finishes.
// It returns 0 when both are held, 1 when the tenant is busy, 2 when the job is busy.
const tryClaimLocks = `SELECT CASE WHEN pg_try_advisory_xact_lock_shared(` + tenantLock + `)
 THEN CASE WHEN pg_try_advisory_xact_lock(` + jobLock + `) THEN 0 ELSE 2 END
 ELSE 1 END`

const (
	lockFree = iota
	lockTenantBusy
	lockJobBusy

	busyRetry = 150 * time.Millisecond
)

// notDueError reports that a resumed job is scheduled for a later time.
type notDueError struct{ at time.Time }

func (*notDueError) Error() string { return "queue: job not due" }

// verdict is what a claim step decided, when it did not fail. A verdict other than proceed
// is reported to the caller after the transaction commits, because the step changed the
// schedule and that change must stick.
type verdict uint8

const (
	proceed verdict = iota
	deferred
	rescheduled
)

func (v verdict) err() error {
	switch v {
	case deferred:
		return ErrDeferred
	case rescheduled:
		return errRescheduled
	case proceed:
		return nil
	}
	return nil
}

// claimRequest is one attempt to claim. An empty key asks the scheduler for the next job
// among the supported kinds; a key resumes that gated job with the caller's secret.
type claimRequest struct {
	key    string
	secret string
	can    supported
}

func (c claimRequest) direct() bool { return c.key != "" }

// claim leases a job, or returns why none was leased. Outcomes that changed the schedule
// (a deferral, a reschedule) commit their change and then return their sentinel error.
// Nothing in the transaction leaves the database: a claim never waits on a network.
func (s *Store) claim(ctx context.Context, req claimRequest) (*Run, error) {
	var (
		run   *Run
		after verdict
	)
	err := pg.InTx(ctx, s.pool, func(tx pgx.Tx) error {
		var err error
		run, after, err = s.claimTx(ctx, tx, req)
		return err
	})
	if err != nil {
		return nil, err
	}
	if after != proceed {
		return nil, after.err()
	}
	return run, nil
}

// claimTx returns a run, or a verdict to report after the transaction commits, or an error
// that rolls it back.
func (s *Store) claimTx(ctx context.Context, tx pgx.Tx, req claimRequest) (*Run, verdict, error) {
	job, err := s.selectCandidate(ctx, tx, req)
	if err != nil {
		return nil, proceed, err
	}
	after, err := lockCandidate(ctx, tx, req, job)
	if after != proceed || err != nil {
		return nil, after, err
	}
	if req.direct() && job.RunAt.After(s.clock.Now()) {
		return nil, proceed, &notDueError{at: job.RunAt}
	}
	if job.State == StateParked {
		// A parked job is due only for its budget requeue: return it to the schedule.
		return nil, rescheduled, requeueParked(ctx, tx, job.Key)
	}
	action := rules.OnClaim(rules.Claimed{
		Leased:       job.State == StateLeased,
		Blocked:      job.State == StateBlocked,
		Gated:        job.Gated,
		Initializing: job.Initializing,
		HasSecret:    req.secret != "",
		HasIntent:    job.intent != nil,
		Attempts:     job.Attempts,
		MaxAttempts:  s.cfg.MaxAttempts,
	})
	if action == rules.ClaimReblock {
		return nil, rescheduled, s.reblock(ctx, tx, job.Key)
	}
	leased, err := s.lease(ctx, tx, req, job, action)
	if err != nil {
		return nil, proceed, err
	}
	identity := lease{tenant: leased.Tenant, key: leased.Key, token: leased.Token}
	return &Run{job: leased, secret: req.secret, lease: identity, store: s}, proceed, nil
}

func (s *Store) selectCandidate(ctx context.Context, tx pgx.Tx, req claimRequest) (Job, error) {
	if !req.direct() {
		return scan(tx.QueryRow(ctx, candidate, req.can.kinds, req.can.formats))
	}
	var expired bool
	job, err := scan(tx.QueryRow(ctx, direct, req.key), &expired)
	if err != nil {
		return Job{}, err
	}
	switch {
	case job.State != StateBlocked || job.Initializing || expired:
		return Job{}, ErrState
	case !s.kinds.runs(job.Kind, job.Format):
		return Job{}, fmt.Errorf("%w: kind %q format %d", ErrUndeclared, job.Kind, job.Format)
	}
	return job, nil
}

// lockCandidate takes the claim locks. When one is busy it puts the work off briefly and
// returns the sentinel to hand back after commit.
func lockCandidate(ctx context.Context, tx pgx.Tx, req claimRequest, job Job) (verdict, error) {
	var busy int
	if err := tx.QueryRow(ctx, tryClaimLocks, job.Tenant, job.Key).Scan(&busy); err != nil {
		return proceed, fmt.Errorf("claim locks: %w", err)
	}
	switch {
	case busy == lockFree:
		return proceed, nil
	case req.direct():
		return proceed, ErrDeferred
	case busy == lockTenantBusy:
		return deferred, deferTenant(ctx, tx, job.Tenant, busyRetry)
	default:
		return rescheduled, postpone(ctx, tx, job.Key)
	}
}

func postpone(ctx context.Context, tx pgx.Tx, key string) error {
	_, err := tx.Exec(ctx,
		"UPDATE queue_jobs SET ready_at=clock_timestamp()+$2*interval '1 microsecond' WHERE job_key=$1",
		key, busyRetry.Microseconds())
	if err != nil {
		return fmt.Errorf("reschedule busy job: %w", err)
	}
	return nil
}

func deferTenant(ctx context.Context, tx pgx.Tx, tenant string, delay time.Duration) error {
	_, err := tx.Exec(ctx,
		"UPDATE queue_tenants SET check_after=clock_timestamp()+$2*interval '1 microsecond' WHERE uid=$1",
		tenant, delay.Microseconds())
	if err != nil {
		return fmt.Errorf("defer tenant: %w", err)
	}
	return nil
}

func requeueParked(ctx context.Context, tx pgx.Tx, key string) error {
	_, err := tx.Exec(ctx, `UPDATE queue_jobs SET state='ready',attempts=0,deterministic_attempts=0,
reconcile_attempts=0,reason=NULL,ready_at=clock_timestamp(),updated_at=clock_timestamp() WHERE job_key=$1`, key)
	if err != nil {
		return fmt.Errorf("requeue parked job: %w", err)
	}
	return nil
}

// reblock returns a gated job to waiting for its secret. The attempt its dead holder was
// charged stays spent.
func (s *Store) reblock(ctx context.Context, tx pgx.Tx, key string) error {
	_, err := tx.Exec(ctx, `UPDATE queue_jobs SET state='blocked',lease_until=NULL,lane_head=false,
ready_at=clock_timestamp()+$2*interval '1 microsecond',blocked_since=clock_timestamp(),
updated_at=clock_timestamp() WHERE job_key=$1`, key, s.cfg.GateTimeout.Microseconds())
	if err != nil {
		return fmt.Errorf("reblock gated job: %w", err)
	}
	return nil
}

// lease issues a new fencing token, counts the attempt and advances the tenant's turn in
// one statement, so a claim by a worker that later dies has already been charged.
func (s *Store) lease(ctx context.Context, tx pgx.Tx, req claimRequest, job Job, action rules.Claim) (Job, error) {
	intent, transient := s.intent(job, action)
	var subMicro time.Duration
	err := tx.QueryRow(ctx, `WITH turn AS (
 UPDATE queue_tenants SET last_claim=clock_timestamp() WHERE uid=$7 AND $8
)
UPDATE queue_jobs AS j SET state='leased',
lease_token=nextval('queue_lease_token'),lease_until=clock_timestamp()+$2*interval '1 microsecond',
ready_at=clock_timestamp()+$2*interval '1 microsecond',
attempts=$3+1,deterministic_attempts=$4,reason=NULL,updated_at=clock_timestamp(),
lane_head=(order_key IS NOT NULL),intent=$5,intent_transient=$6
WHERE job_key=$1 RETURNING lease_token,attempts,order_at,order_sub_us,
$9 AND EXISTS (SELECT 1 FROM queue_jobs c WHERE c.uid=j.uid AND c.kind=j.kind AND c.order_key=j.order_key
AND c.outcome='success' AND (c.order_at,c.order_sub_us,c.order_sort,c.job_key)>
(j.order_at,j.order_sub_us,j.order_sort,j.job_key))`,
		job.Key, s.cfg.Lease.Microseconds(), job.Attempts, job.DeterministicAttempts, intent, transient,
		job.Tenant, !req.direct(), s.kinds.kinds[job.Kind].paidProcessing,
	).Scan(&job.Token, &job.Attempts, &job.CaptureAt, &subMicro, &job.LateCapture)
	if err != nil {
		return Job{}, fmt.Errorf("lease: %w", err)
	}
	job.CaptureAt = job.CaptureAt.Add(subMicro)
	job.State = StateLeased
	job.Reason = nil
	job.intent = intent
	job.intentTransient = transient
	return job, nil
}

// intent returns the terminal intent this claim must reconcile, if any: one already
// recorded, or one the claim itself discovered.
func (s *Store) intent(job Job, action rules.Claim) (*Cause, bool) {
	switch action {
	case rules.ClaimReconcile:
		return job.intent, job.intentTransient
	case rules.ClaimLeaseExpired:
		cause := CauseLeaseExpired
		return &cause, true
	case rules.ClaimGateAbandoned:
		cause := s.cfg.GateAbandoned
		return &cause, false
	case rules.ClaimWork, rules.ClaimReblock:
		return nil, false
	}
	return nil, false
}

func (s *Store) renew(ctx context.Context, held lease) error {
	tag, err := s.heartbeat.Exec(ctx, `UPDATE queue_jobs SET
lease_until=clock_timestamp()+$3*interval '1 microsecond',ready_at=clock_timestamp()+$3*interval '1 microsecond'
WHERE job_key=$1 AND lease_token=$2 AND state='leased' AND lease_until > clock_timestamp()`,
		held.key, held.token, s.cfg.Lease.Microseconds())
	if err != nil {
		return fmt.Errorf("renew lease: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrLease
	}
	return nil
}
