package queue

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

// Condition identifies an owner fact checked at intake.
type Condition string

// Entitlement is the platform-funded processing condition.
const Entitlement Condition = "entitlement"

// EntitlementSnapshot is an authoritative observation. Positive revisions increase
// across both exhaustion and funding transitions. Zero denotes an unversioned account.
type EntitlementSnapshot struct {
	// ChangedAt is the source time, used to measure event-to-release latency.
	ChangedAt  time.Time
	Generation int64
	Exhausted  bool
}

type fundingWait struct {
	conditionDeadline, timedDeadline *time.Time
	timedGeneration                  int64
}

func (cfg Config) fundingWait(n NewJob, generation int64) (fundingWait, error) {
	if n.CustodyDeadline.IsZero() || n.AudioDuration <= 0 || n.Gated || n.Initializing {
		return fundingWait{}, fmt.Errorf("%w: held intake requires custody deadline and duration on a plain job", ErrState)
	}
	if cfg.TimeOnlyEntitlementHold {
		return fundingWait{timedDeadline: &n.CustodyDeadline, timedGeneration: generation}, nil
	}
	return fundingWait{conditionDeadline: &n.CustodyDeadline}, nil
}

// enqueuePaid locks the same owner row as an entitlement update, including first admission.
func (sc *Scope) enqueuePaid(ctx context.Context, n NewJob) (Job, bool, error) {
	var job Job
	store := sc.store
	var inserted bool
	tenant := sc.tenant
	err := pgx.BeginFunc(ctx, sc.conn, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, "INSERT INTO queue_tenants(uid) VALUES ($1) ON CONFLICT DO NOTHING", tenant); err != nil {
			return err
		}
		var held bool
		var generation int64
		if err := tx.QueryRow(ctx, "SELECT entitlement_check_at IS NOT NULL,entitlement_generation FROM queue_tenants WHERE uid=$1 FOR UPDATE", tenant).Scan(&held, &generation); err != nil {
			return err
		}
		var wait fundingWait
		if held {
			// An admission replay keeps the first decision, even if this caller has
			// no custody metadata or a newer owner observation.
			existing, err := scan(tx.QueryRow(ctx, "SELECT "+columns+" FROM queue_jobs j WHERE uid=$1 AND job_key=$2", tenant, n.Key))
			if err == nil {
				job = existing
				return nil
			}
			if !errors.Is(err, ErrAbsent) {
				return err
			}
			wait, err = store.cfg.fundingWait(n, generation)
			if err != nil {
				return err
			}
		}
		var err error
		job, inserted, err = store.insert(ctx, tx, n, wait)
		return err
	})
	if err == nil && inserted && job.State != StateWaiting {
		sc.store.signal()
	}
	return job, inserted, err
}

// HoldCondition records verified exhaustion for subsequent paid admissions.
func (s *Store) HoldCondition(ctx context.Context, tenant string, condition Condition, generation int64) error {
	return s.changeCondition(ctx, tenant, condition, EntitlementSnapshot{Generation: generation, Exhausted: true})
}

// Release handles a funding, grant or period change. Stale events cannot clear a newer hold.
func (s *Store) Release(ctx context.Context, tenant string, condition Condition, generation int64) error {
	return s.changeCondition(ctx, tenant, condition, EntitlementSnapshot{Generation: generation})
}

func (s *Store) changeCondition(ctx context.Context, tenant string, condition Condition, snapshot EntitlementSnapshot) error {
	if condition != Entitlement || snapshot.Generation <= 0 {
		return ErrState
	}
	return s.Tenant(ctx, tenant, func(sc *Scope) error { return sc.ObserveEntitlement(ctx, snapshot) })
}

// ObserveEntitlement applies the same fact at intake and on event delivery. The owner
// revision and all released units commit together. An error leaves the revision replayable.
func (sc *Scope) ObserveEntitlement(ctx context.Context, snapshot EntitlementSnapshot) error {
	if snapshot.Generation <= 0 {
		return ErrState
	}
	var released int64
	tenant := sc.tenant
	err := pgx.BeginFunc(ctx, sc.conn, func(tx pgx.Tx) error {
		tag, err := tx.Exec(ctx, `INSERT INTO queue_tenants(uid,entitlement_generation,entitlement_check_at)
VALUES ($1,$2,CASE WHEN $3 THEN statement_timestamp()+interval '1 hour' END)
ON CONFLICT(uid) DO UPDATE SET entitlement_generation=excluded.entitlement_generation,
entitlement_check_at=excluded.entitlement_check_at
WHERE queue_tenants.entitlement_generation<excluded.entitlement_generation`, tenant, snapshot.Generation, snapshot.Exhausted)
		if err != nil || tag.RowsAffected() == 0 || snapshot.Exhausted {
			return err
		}
		// Use one statement timestamp for the deadline decision.
		err = tx.QueryRow(ctx, `WITH settled AS (UPDATE queue_jobs SET
state=CASE WHEN custody_deadline<=statement_timestamp() THEN 'completed' ELSE 'ready' END,
outcome=CASE WHEN custody_deadline<=statement_timestamp() THEN 'expired_unfunded' END,
ready_at=CASE WHEN custody_deadline>statement_timestamp() THEN greatest(run_at,statement_timestamp()) END,
owed_since=statement_timestamp(),
order_key=held_order_key,held_order_key=NULL,custody_deadline=NULL,updated_at=statement_timestamp()
WHERE uid=$1 AND custody_deadline IS NOT NULL RETURNING state),
tally AS (SELECT count(*) FILTER (WHERE state='ready') AS released,
                 count(*) FILTER (WHERE state='completed') AS expired FROM settled),
count_expired AS (UPDATE queue_settings SET expired_unfunded=expired_unfunded+tally.expired
                  FROM tally WHERE tally.expired>0)
SELECT released FROM tally`, tenant).Scan(&released)
		return err
	})
	if err == nil && released > 0 {
		if !snapshot.ChangedAt.IsZero() {
			sc.store.observer.EntitlementReleased(max(0, sc.store.clock.Now().Sub(snapshot.ChangedAt)))
		}
		sc.store.signal()
	}
	return err
}

// EntitlementReader resolves the current fact under the tenant's erasure barrier.
type EntitlementReader func(context.Context, Admitting, string) (EntitlementSnapshot, error)

// CheckEntitlements settles expired custody and revisits due owners once per hour.
// Claiming a check advances its timer before the external read so replicas share the work.
func (s *Store) CheckEntitlements(ctx context.Context, read EntitlementReader) error {
	if _, err := s.pool.Exec(ctx, `WITH expired AS (UPDATE queue_jobs SET state='completed',outcome='expired_unfunded',
custody_deadline=NULL,held_order_key=NULL,timed_deadline=NULL,timed_generation=0,
ready_at=NULL,lease_until=NULL,lane_head=false,updated_at=statement_timestamp()
WHERE outcome IS NULL AND (custody_deadline<=statement_timestamp() OR timed_deadline<=statement_timestamp()) RETURNING 1),
tally AS (SELECT count(*) AS n FROM expired)
UPDATE queue_settings SET expired_unfunded=expired_unfunded+tally.n FROM tally WHERE tally.n>0`); err != nil {
		return fmt.Errorf("expire unfunded: %w", err)
	}
	if s.cfg.TimeOnlyEntitlementHold {
		return s.restoreTimedHolds(ctx)
	}
	rows, err := s.pool.Query(ctx, `UPDATE queue_tenants SET entitlement_check_at=statement_timestamp()+interval '1 hour'
WHERE uid IN (SELECT uid FROM queue_tenants WHERE entitlement_check_at<=statement_timestamp()
AND EXISTS (SELECT 1 FROM queue_jobs j WHERE j.uid=queue_tenants.uid AND j.custody_deadline IS NOT NULL)
ORDER BY entitlement_check_at LIMIT 100 FOR UPDATE SKIP LOCKED) RETURNING uid`)
	if err != nil {
		return fmt.Errorf("claim entitlement checks: %w", err)
	}
	owners, err := pgx.CollectRows(rows, pgx.RowTo[string])
	if err != nil {
		return err
	}
	var failures error
	for _, owner := range owners {
		err := s.Tenant(ctx, owner, func(sc *Scope) error {
			fact, err := read(ctx, sc.Admitting(), owner)
			if err != nil {
				return err
			}
			return sc.ObserveEntitlement(ctx, fact)
		})
		if err != nil && !errors.Is(err, ErrErased) {
			failures = errors.Join(failures, err)
		}
	}
	return failures
}

// Convert on every maintenance tick so a rolling switch also catches admissions
// committed by the last condition-enabled replica. No funding revision is advanced.
func (s *Store) restoreTimedHolds(ctx context.Context) error {
	tag, err := s.pool.Exec(ctx, `UPDATE queue_jobs j SET timed_deadline=j.custody_deadline,
timed_generation=t.entitlement_generation,custody_deadline=NULL,order_key=j.held_order_key,
held_order_key=NULL,state='ready',ready_at=j.run_at,updated_at=statement_timestamp()
FROM queue_tenants t WHERE t.uid=j.uid AND j.custody_deadline>statement_timestamp()`)
	if err != nil {
		return fmt.Errorf("restore timed funding holds: %w", err)
	}
	if tag.RowsAffected() > 0 {
		s.signal()
	}
	return nil
}

// AuthorizeTimedFunding is called under the guard before the first paid call. Only
// a newer funded observation can spend. Clearing the refusal before the call keeps
// its result recoverable if a retry crosses the original custody deadline.
func (r *Run) AuthorizeTimedFunding(ctx context.Context, fact EntitlementSnapshot) error {
	if r.job.timedGeneration == 0 {
		return nil
	}
	if fact.Exhausted || fact.Generation <= r.job.timedGeneration {
		return Classify(ErrDeferred, Hold(CauseAllowanceExhausted, 5*time.Minute))
	}
	tag, err := r.store.pool.Exec(ctx, `UPDATE queue_jobs j SET timed_generation=0,timed_deadline=NULL,owed_since=statement_timestamp()
WHERE job_key=$1 AND lease_token=$2 AND state='leased' AND lease_until>clock_timestamp()
AND timed_deadline>clock_timestamp() AND NOT EXISTS
(SELECT 1 FROM queue_tenants t WHERE t.uid=j.uid AND t.entitlement_generation>=$3 AND t.entitlement_check_at IS NOT NULL)`, r.lease.key, r.lease.token, fact.Generation)
	if err != nil {
		return fmt.Errorf("clear timed funding hold: %w", err)
	}
	if tag.RowsAffected() == 0 {
		// The expiry sweep owns terminal accounting. A stale worker cannot spend.
		return Classify(ErrDeferred, Yield(CauseAllowanceExhausted, time.Minute))
	}
	return nil
}
