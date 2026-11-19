package queue

import (
	"context"
	"errors"
	"fmt"
	"sync/atomic"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
)

// Scope is a tenant's admission context: one pinned connection holding the shared erasure
// barrier. Everything done through it either completes before an erase or is refused after.
type Scope struct {
	store  *Store
	conn   *pgxpool.Conn
	tenant string
	open   *atomic.Bool
}

// Admitting returns the proof that a call runs inside this scope, for a port method that
// reaches outside the process during admission.
func (sc *Scope) Admitting() Admitting { return Admitting{open: sc.open, tenant: sc.tenant} }

// Tenant runs fn while holding the tenant's shared erasure barrier. It returns ErrErased
// for a tenant that was erased.
func (s *Store) Tenant(ctx context.Context, tenant string, fn func(*Scope) error) error {
	return s.withTenant(ctx, tenant, false, func(sc *Scope) error {
		var erased bool
		err := sc.conn.QueryRow(ctx,
			"SELECT EXISTS(SELECT 1 FROM queue_erasure WHERE tenant_hash="+tenantHashSQL+")", tenant).Scan(&erased)
		if err != nil {
			return fmt.Errorf("check erasure: %w", err)
		}
		if erased {
			return ErrErased
		}
		return fn(sc)
	})
}

func (s *Store) withTenant(ctx context.Context, tenant string, exclusive bool, fn func(*Scope) error) (err error) {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return fmt.Errorf("acquire connection: %w", err)
	}
	defer conn.Release()
	lock := "pg_advisory_lock_shared"
	if exclusive {
		lock = "pg_advisory_lock"
	}
	if _, lockErr := conn.Exec(ctx, "SELECT "+lock+"("+tenantLock+")", tenant); lockErr != nil {
		// The lock state of this session is unknown: do not return it to the pool.
		return errors.Join(fmt.Errorf("tenant lock: %w", lockErr), discard(ctx, conn))
	}
	// Registered before fn runs, so the lock is dropped even if fn panics.
	defer func() { err = errors.Join(err, unlock(ctx, conn)) }()
	open := &atomic.Bool{}
	open.Store(true)
	defer open.Store(false)
	return fn(&Scope{store: s, conn: conn, tenant: tenant, open: open})
}

// unlock releases every session lock on conn. It runs after the caller's context may be
// cancelled, so it uses its own deadline; if it fails the connection is closed, which
// releases the locks server-side.
func unlock(ctx context.Context, conn *pgxpool.Conn) error {
	cleanup, cancel := pg.Cleanup(ctx, 2*time.Second)
	defer cancel()
	if _, err := conn.Exec(cleanup, "SELECT pg_advisory_unlock_all()"); err != nil {
		// Closing the connection releases the locks server-side. The unlock failure is
		// still returned: the caller must not report a clean finish.
		return errors.Join(fmt.Errorf("release session locks: %w", err), discard(ctx, conn))
	}
	return nil
}

// discard closes the underlying connection so the pool drops it.
func discard(ctx context.Context, conn *pgxpool.Conn) error {
	cleanup, cancel := pg.Cleanup(ctx, 3*time.Second)
	defer cancel()
	if err := conn.Conn().Close(cleanup); err != nil {
		return fmt.Errorf("close pinned connection: %w", err)
	}
	return nil
}

// Subject serializes admissions for one subject of one kind inside a Tenant callback. Call
// it at most once per scope; the lock is released when the scope ends.
func (sc *Scope) Subject(ctx context.Context, kind, subject string, fn func() error) error {
	key := fmt.Sprintf("%d:%s%d:%s%s", len(sc.tenant), sc.tenant, len(kind), kind, subject)
	if _, err := sc.conn.Exec(ctx, "SELECT pg_advisory_lock("+subjectLock+")", key); err != nil {
		return fmt.Errorf("subject lock: %w", err)
	}
	return fn()
}

// Get returns this tenant's job with the given key.
func (sc *Scope) Get(ctx context.Context, key string) (Job, error) {
	return scan(sc.conn.QueryRow(ctx,
		"SELECT "+columns+" FROM queue_jobs j WHERE uid=$1 AND job_key=$2", sc.tenant, key))
}

// Active returns the oldest job for the subject that is still initializing.
func (sc *Scope) Active(ctx context.Context, kind, subject string) (Job, error) {
	return scan(sc.conn.QueryRow(ctx, "SELECT "+columns+` FROM queue_jobs j
WHERE uid=$1 AND kind=$2 AND subject=$3 AND outcome IS NULL AND initializing
ORDER BY created_at,job_key LIMIT 1`, sc.tenant, kind, subject))
}

const insertJob = `WITH tenant AS (
 INSERT INTO queue_tenants(uid) VALUES ($2) ON CONFLICT DO NOTHING
), lane AS (
 INSERT INTO queue_lanes(uid,kind,order_key) SELECT $2,$3,$9::text WHERE $9 IS NOT NULL
 ON CONFLICT DO NOTHING
), j AS (
 INSERT INTO queue_jobs AS q (job_key,uid,kind,subject,meta,budget_allowed,gated,initializing,order_key,
                        order_at,order_sub_us,order_sort,state,step,ready_at,run_at,blocked_since,format)
 SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18
 ON CONFLICT DO NOTHING
 RETURNING ` + rawColumns + `
)
SELECT ` + columns + " FROM j"

// Enqueue inserts n and reports whether it was new. An existing key returns the first
// job unchanged: the first enqueue fixes the job's input.
func (sc *Scope) Enqueue(ctx context.Context, n NewJob) (Job, bool, error) {
	if err := sc.admissible(n); err != nil {
		return Job{}, false, err
	}
	now := sc.store.clock.Now()
	n = withDefaults(n, now)
	state, due, since := initialSchedule(n, now, sc.store.cfg.GateTimeout)
	j, err := scan(sc.conn.QueryRow(ctx, insertJob, n.Key, n.Tenant, n.Kind, n.Subject, n.Meta, n.BudgetAllowed,
		n.Gated, n.Initializing, n.OrderKey, n.OrderAt, n.OrderAt.Nanosecond()%1000, n.SortKey, state, n.Step,
		due, n.RunAt, since, n.Format))
	if errors.Is(err, ErrAbsent) {
		existing, getErr := sc.Get(ctx, n.Key)
		return existing, false, getErr
	}
	if err != nil {
		return Job{}, false, err
	}
	sc.store.signal()
	return j, true, nil
}

// admissible rejects a job this binary has no declaration for, before it reaches the table:
// an undeclared kind, format or step would otherwise sit in the queue with no replica able
// to run it.
func (sc *Scope) admissible(n NewJob) error {
	kinds := sc.store.kinds
	switch {
	case n.Tenant != sc.tenant || n.Key == "":
		return ErrState
	case !kinds.runs(n.Kind, n.Format):
		return fmt.Errorf("%w: kind %q format %d", ErrUndeclared, n.Kind, n.Format)
	case !kinds.hasStep(n.Kind, n.Step):
		return fmt.Errorf("%w: step %q of kind %q", ErrUndeclared, n.Step, n.Kind)
	case n.Gated && n.OrderKey != nil:
		return fmt.Errorf("%w: a gated job cannot be in an ordered lane", ErrState)
	}
	return nil
}

func withDefaults(n NewJob, now time.Time) NewJob {
	if n.Meta == nil {
		n.Meta = []byte("null")
	}
	if n.RunAt.IsZero() {
		n.RunAt = now
	}
	if n.OrderAt.IsZero() {
		n.OrderAt = n.RunAt
	}
	if n.SortKey == "" {
		n.SortKey = n.Key
	}
	return n
}

// initialSchedule decides a new job's first state, when it is next looked at, and when its
// gate wait began. An initializing job is revisited after a second in case admission died.
func initialSchedule(n NewJob, now time.Time, gateTimeout time.Duration) (State, time.Time, *time.Time) {
	switch {
	case n.Initializing && n.Gated:
		return StateBlocked, now.Add(time.Second), nil
	case n.Initializing:
		return StateReady, now.Add(time.Second), nil
	case n.Gated:
		return StateBlocked, now.Add(gateTimeout), &now
	default:
		return StateReady, n.RunAt, nil
	}
}

// Enqueue inserts n under its tenant's erasure barrier. See Scope.Enqueue.
func (s *Store) Enqueue(ctx context.Context, n NewJob) (Job, error) {
	var job Job
	err := s.Tenant(ctx, n.Tenant, func(sc *Scope) error {
		var err error
		job, _, err = sc.Enqueue(ctx, n)
		return err
	})
	return job, err
}

// Activate releases an initializing job once admission has bound it to its subject. If a
// worker is already repairing the job, that worker owns the transition and this is a no-op.
func (sc *Scope) Activate(ctx context.Context, key string) error {
	_, err := sc.conn.Exec(ctx, `UPDATE queue_jobs SET initializing=false,
state=CASE WHEN gated THEN 'blocked' ELSE 'ready' END,
ready_at=CASE WHEN gated THEN clock_timestamp()+$3*interval '1 microsecond' ELSE run_at END,
blocked_since=CASE WHEN gated THEN clock_timestamp() END,updated_at=clock_timestamp()
WHERE uid=$1 AND job_key=$2 AND initializing AND state IN ('ready','waiting','blocked')`,
		sc.tenant, key, sc.store.cfg.GateTimeout.Microseconds())
	if err != nil {
		return fmt.Errorf("activate: %w", err)
	}
	sc.store.signal()
	return nil
}

// CancelInitialization removes an initializing job that no worker has touched, after the
// subject's owner explicitly refused the admission.
func (sc *Scope) CancelInitialization(ctx context.Context, key string) error {
	_, err := sc.conn.Exec(ctx, `DELETE FROM queue_jobs
WHERE uid=$1 AND job_key=$2 AND initializing AND attempts=0 AND state<>'leased'`, sc.tenant, key)
	if err != nil {
		return fmt.Errorf("cancel initialization: %w", err)
	}
	return nil
}

// Erase removes every row of the tenant and records a salted tombstone, all under the
// exclusive barrier, which first waits for the tenant's in-flight guarded calls to finish.
// It then runs eraseRemote, still under the barrier. A repeated call resumes an erase whose
// remote step did not complete.
func (s *Store) Erase(ctx context.Context, tenant string, eraseRemote func() error) error {
	return s.withTenant(ctx, tenant, true, func(sc *Scope) error {
		var complete bool
		err := sc.conn.QueryRow(ctx, `WITH purge AS (DELETE FROM queue_tenants WHERE uid=$1)
INSERT INTO queue_erasure(tenant_hash) VALUES (`+tenantHashSQL+`)
ON CONFLICT(tenant_hash) DO UPDATE SET tenant_hash=EXCLUDED.tenant_hash RETURNING completed`, tenant).Scan(&complete)
		if err != nil {
			return fmt.Errorf("erase: %w", err)
		}
		if complete {
			return nil
		}
		if remoteErr := eraseRemote(); remoteErr != nil {
			return remoteErr
		}
		_, err = sc.conn.Exec(ctx, "UPDATE queue_erasure SET completed=true WHERE tenant_hash="+tenantHashSQL, tenant)
		if err != nil {
			return fmt.Errorf("complete erase: %w", err)
		}
		return nil
	})
}
