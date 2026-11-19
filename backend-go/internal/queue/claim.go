package queue

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
	"github.com/BasedHardware/omi/backend-go/internal/queue/rules"
)

// candidate picks the next job fairly: the tenant that was served longest ago, then that
// tenant's earliest due job. An ordered lane offers only its current head (or, with no head,
// its first member in lane order), so a lane never runs two jobs at once. SKIP LOCKED lets
// replicas dispatch concurrently without waiting on each other.
const candidate = `
 SELECT ` + columns + ` FROM queue_tenants t
 CROSS JOIN LATERAL (
   SELECT q.job_key,q.uid,q.kind,q.subject,q.meta,q.checkpoint,q.gated,q.initializing,q.state,q.step,
          q.attempts,q.deterministic_attempts,q.budget_allowed,q.budget_requeues,q.lease_token,q.reason,
          q.outcome,q.created_at,q.updated_at,q.run_at,q.intent,q.intent_transient
   FROM (
     (SELECT u.job_key,u.ready_at FROM queue_jobs u
       WHERE u.uid=t.uid AND u.ready_at <= statement_timestamp()
         AND (u.order_key IS NULL OR u.state='parked')
       ORDER BY u.ready_at,u.job_key LIMIT 1)
     UNION ALL
     (SELECT o.job_key,o.ready_at FROM queue_lanes l
       JOIN queue_jobs o ON o.job_key=COALESCE(
         (SELECT h.job_key FROM queue_jobs h WHERE h.kind=l.kind AND h.order_key=l.order_key AND h.lane_head),
         (SELECT p.job_key FROM queue_jobs p
           WHERE p.kind=l.kind AND p.order_key=l.order_key AND p.state NOT IN ('parked','completed')
           ORDER BY p.order_at,p.order_sub_us,p.order_sort,p.job_key LIMIT 1)
       )
       WHERE l.uid=t.uid AND o.uid=t.uid AND o.ready_at <= statement_timestamp()
       ORDER BY o.ready_at,o.job_key LIMIT 1)
   ) available JOIN queue_jobs q USING (job_key)
   WHERE q.ready_at <= statement_timestamp()
   ORDER BY available.ready_at,available.job_key LIMIT 1 FOR UPDATE OF q SKIP LOCKED
 ) j
 WHERE t.check_after<=statement_timestamp() AND EXISTS (
   SELECT 1 FROM queue_jobs d WHERE d.uid=t.uid AND d.ready_at<=statement_timestamp()
 )
 ORDER BY t.last_claim,t.uid LIMIT 1 FOR UPDATE OF t SKIP LOCKED`

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

// claimRequest is one attempt to claim. An empty key asks the scheduler for the next job;
// a key resumes that gated job with the caller's secret.
type claimRequest struct {
	key    string
	secret string
	check  Preflight
}

func (c claimRequest) direct() bool { return c.key != "" }

// claim leases a job, or returns why none was leased. Outcomes that changed the schedule
// (a deferral, a reschedule) commit their change and then return their sentinel error.
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
	job, err := selectCandidate(ctx, tx, req)
	if err != nil {
		return nil, proceed, err
	}
	after, err := lockCandidate(ctx, tx, req, job)
	if after != proceed || err != nil {
		return nil, after, err
	}
	var data any
	if req.check != nil {
		delay, payload := req.check(ctx, job)
		data = payload
		if delay > 0 {
			after, deferErr := putOff(ctx, tx, req, job.Tenant, delay)
			return nil, after, deferErr
		}
	}
	if req.direct() && job.RunAt.After(s.clock.Now()) {
		return nil, proceed, &notDueError{at: job.RunAt}
	}
	if job.State == StateParked {
		// A parked job is due only for its budget requeue: return it to the schedule.
		return nil, rescheduled, requeueParked(ctx, tx, job.Key)
	}
	leased, err := s.lease(ctx, tx, req, job)
	if err != nil {
		return nil, proceed, err
	}
	return &Run{Job: leased, Secret: req.secret, Preflight: data, store: s}, proceed, nil
}

func selectCandidate(ctx context.Context, tx pgx.Tx, req claimRequest) (Job, error) {
	if !req.direct() {
		return scan(tx.QueryRow(ctx, candidate))
	}
	job, err := scan(tx.QueryRow(ctx,
		"SELECT "+columns+" FROM queue_jobs j WHERE j.job_key=$1 FOR UPDATE OF j", req.key))
	if err != nil {
		return Job{}, err
	}
	if job.State != StateBlocked || job.Initializing {
		return Job{}, ErrState
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

// putOff handles a preflight deferral. A direct resume holds no tenant row lock, so it is
// refused without moving the scheduler's timer.
func putOff(ctx context.Context, tx pgx.Tx, req claimRequest, tenant string, delay time.Duration) (verdict, error) {
	if req.direct() {
		return proceed, ErrDeferred
	}
	return deferred, deferTenant(ctx, tx, tenant, delay)
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
reason=NULL,ready_at=clock_timestamp(),updated_at=clock_timestamp() WHERE job_key=$1`, key)
	if err != nil {
		return fmt.Errorf("requeue parked job: %w", err)
	}
	return nil
}

// lease issues a new fencing token and counts the attempt in the same statement, so a
// claim by a worker that later dies has already been charged.
func (s *Store) lease(ctx context.Context, tx pgx.Tx, req claimRequest, job Job) (Job, error) {
	recovery, transient := s.recovery(job, req.secret != "")
	err := tx.QueryRow(ctx, `UPDATE queue_jobs SET state='leased',
lease_token=nextval('queue_lease_token'),lease_until=clock_timestamp()+$2*interval '1 microsecond',
ready_at=clock_timestamp()+$2*interval '1 microsecond',
attempts=$3+1,deterministic_attempts=$4,reason=NULL,updated_at=clock_timestamp(),
lane_head=(order_key IS NOT NULL),intent=$5,intent_transient=$6
WHERE job_key=$1 RETURNING lease_token,attempts`,
		job.Key, s.cfg.Lease.Microseconds(), job.Attempts, job.DeterministicAttempts, recovery, transient,
	).Scan(&job.Token, &job.Attempts)
	if err != nil {
		return Job{}, fmt.Errorf("lease: %w", err)
	}
	if !req.direct() {
		_, err = tx.Exec(ctx, "UPDATE queue_tenants SET last_claim=clock_timestamp() WHERE uid=$1", job.Tenant)
		if err != nil {
			return Job{}, fmt.Errorf("advance tenant turn: %w", err)
		}
	}
	job.State = StateLeased
	job.Reason = nil
	job.intent = recovery
	job.intentTransient = transient
	return job, nil
}

// recovery returns the terminal intent this claim must reconcile, if any: one already
// recorded, or one the claim itself discovers.
func (s *Store) recovery(job Job, hasSecret bool) (*Cause, bool) {
	if job.intent != nil {
		return job.intent, job.intentTransient
	}
	switch rules.OnClaim(rules.Claimed{
		Leased:       job.State == StateLeased,
		Blocked:      job.State == StateBlocked,
		Initializing: job.Initializing,
		HasSecret:    hasSecret,
		Attempts:     job.Attempts,
		MaxAttempts:  s.cfg.MaxAttempts,
	}) {
	case rules.RecoveryLeaseExpired:
		cause := CauseLeaseExpired
		return &cause, true
	case rules.RecoveryGateAbandoned:
		cause := s.cfg.GateAbandoned
		return &cause, false
	case rules.RecoveryNone:
		return nil, false
	}
	return nil, false
}

func (s *Store) renew(ctx context.Context, job Job) error {
	tag, err := s.heartbeat.Exec(ctx, `UPDATE queue_jobs SET
lease_until=clock_timestamp()+$3*interval '1 microsecond',ready_at=clock_timestamp()+$3*interval '1 microsecond'
WHERE job_key=$1 AND lease_token=$2 AND state='leased' AND lease_until > clock_timestamp()`,
		job.Key, job.Token, s.cfg.Lease.Microseconds())
	if err != nil {
		return fmt.Errorf("renew lease: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrLease
	}
	return nil
}

// Guard runs fn, a call to an external system, while holding the tenant's shared erasure
// barrier and the job's lock, after confirming the lease is still held. An erase waits for
// it; a takeover cannot overlap it. The external system still needs its own conditional
// write or idempotency key, because a crash after the call cannot be undone here.
func (r *Run) Guard(ctx context.Context, fn func(context.Context) error) error {
	conn, err := r.store.pool.Acquire(ctx)
	if err != nil {
		return fmt.Errorf("acquire connection: %w", err)
	}
	defer conn.Release()
	var active bool
	err = conn.QueryRow(ctx, "SELECT queue_acquire_guard($1,$2,$3)", r.Job.Tenant, r.Job.Key, r.Job.Token).Scan(&active)
	if err != nil {
		return errors.Join(fmt.Errorf("acquire guard: %w", err), unlock(ctx, conn))
	}
	if !active {
		return errors.Join(ErrLease, unlock(ctx, conn))
	}
	return errors.Join(fn(ctx), unlock(ctx, conn))
}
