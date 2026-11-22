package queue

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
)

const (
	// The three advisory-lock namespaces. Tenant before job, always, to avoid deadlock.
	tenantLock  = "hashtextextended($1,447119)"
	jobLock     = "hashtextextended($2,447120)"
	subjectLock = "hashtextextended($1,447121)"

	tenantHashSQL = "(SELECT sha256(erasure_salt || convert_to($1,'UTF8')) FROM queue_settings)"

	mainPoolSpare      = 12
	heartbeatPoolLimit = 4
)

// Store is the queue's database handle. It is safe for concurrent use.
type Store struct {
	pool      *pgxpool.Pool
	heartbeat *pgxpool.Pool
	cfg       Config
	kinds     registry
	observer  Observer
	clock     clock.Clock
	// wake tells one idle dispatcher that work may be claimable now.
	wake chan struct{}
	// rescan tells the schedule watcher that a due time changed, so it must not sleep on.
	rescan chan struct{}
}

// Open validates the policy and the kind declarations, then connects two bounded pools: one
// for work and a small one reserved for lease renewals, so a saturated work pool can never
// starve the heartbeats that keep leases alive.
func Open(
	ctx context.Context, url string, cfg Config, kinds []Kind, observer Observer, c clock.Clock,
) (*Store, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	declared, err := newRegistry(cfg, kinds)
	if err != nil {
		return nil, err
	}
	if c == nil {
		return nil, fmt.Errorf("%w: a clock is required", ErrConfig)
	}
	main, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, fmt.Errorf("parse database url: %w", err)
	}
	main.MaxConns = pg.Int32(cfg.Workers + mainPoolSpare)
	main.ConnConfig.RuntimeParams["statement_timeout"] = "15000"
	main.ConnConfig.RuntimeParams["lock_timeout"] = "12000"
	main.ConnConfig.RuntimeParams["default_transaction_isolation"] = "read committed"
	pool, err := pgxpool.NewWithConfig(ctx, main)
	if err != nil {
		return nil, fmt.Errorf("open pool: %w", err)
	}
	beat := main.Copy()
	beat.MaxConns = pg.Int32(min(heartbeatPoolLimit, cfg.Workers))
	beat.ConnConfig.RuntimeParams["statement_timeout"] = "2000"
	beat.ConnConfig.RuntimeParams["lock_timeout"] = "1000"
	heartbeat, err := pgxpool.NewWithConfig(ctx, beat)
	if err != nil {
		pool.Close()
		return nil, fmt.Errorf("open heartbeat pool: %w", err)
	}
	if observer == nil {
		observer = silent{}
	}
	store := &Store{
		pool: pool, heartbeat: heartbeat, cfg: cfg, kinds: declared, observer: observer,
		clock: c, wake: make(chan struct{}, 1), rescan: make(chan struct{}, 1),
	}
	if err := pool.Ping(ctx); err != nil {
		store.Close()
		return nil, fmt.Errorf("ping: %w", err)
	}
	return store, nil
}

// Causes lists every cause this store accepts, for metrics that must report zeros.
func (s *Store) Causes() []Cause {
	out := make([]Cause, 0, len(s.kinds.causes))
	for c := range s.kinds.causes {
		out = append(out, c)
	}
	return out
}

// Config returns the policy the store was opened with.
func (s *Store) Config() Config { return s.cfg }

// Close releases both pools.
func (s *Store) Close() {
	s.pool.Close()
	s.heartbeat.Close()
}

// Ping checks the database is reachable.
func (s *Store) Ping(ctx context.Context) error {
	if err := s.pool.Ping(ctx); err != nil {
		return fmt.Errorf("ping: %w", err)
	}
	return nil
}

// columns is the one projection of a job row. scan reads exactly these, in this order.
const columns = `j.job_key,j.uid,j.kind,j.format,j.subject,j.meta,j.checkpoint,j.gated,j.initializing,
j.state,j.step,j.attempts,j.deterministic_attempts,j.reconcile_attempts,j.budget_allowed,j.budget_requeues,
j.lease_token,j.reason,j.outcome,j.created_at,j.updated_at,j.run_at,j.intent,j.intent_transient,
(j.order_key IS NOT NULL)`

// rawColumns is the same projection for a subquery or RETURNING list aliased q, keeping
// order_key so the outer query can derive Ordered from it.
const rawColumns = `q.job_key,q.uid,q.kind,q.format,q.subject,q.meta,q.checkpoint,q.gated,q.initializing,
q.state,q.step,q.attempts,q.deterministic_attempts,q.reconcile_attempts,q.budget_allowed,q.budget_requeues,
q.lease_token,q.reason,q.outcome,q.created_at,q.updated_at,q.run_at,q.intent,q.intent_transient,q.order_key`

func scan(row pgx.Row, extra ...any) (Job, error) {
	var j Job
	dest := append([]any{
		&j.Key, &j.Tenant, &j.Kind, &j.Format, &j.Subject, &j.Meta, &j.Checkpoint, &j.Gated, &j.Initializing,
		&j.State, &j.Step, &j.Attempts, &j.DeterministicAttempts, &j.ReconcileAttempts, &j.budgetAllowed,
		&j.BudgetRequeues, &j.Token, &j.Reason, &j.Outcome, &j.CreatedAt, &j.UpdatedAt, &j.RunAt, &j.intent,
		&j.intentTransient, &j.Ordered,
	}, extra...)
	err := row.Scan(dest...)
	if isNoRows(err) {
		return Job{}, ErrAbsent
	}
	if err != nil {
		return Job{}, fmt.Errorf("scan job: %w", err)
	}
	return j, nil
}

// Get returns the job with this key.
func (s *Store) Get(ctx context.Context, key string) (Job, error) {
	return scan(s.pool.QueryRow(ctx, "SELECT "+columns+" FROM queue_jobs j WHERE job_key=$1", key))
}

// Parked lists parked jobs, oldest first. An empty tenant lists every tenant.
func (s *Store) Parked(ctx context.Context, tenant string) ([]Job, error) {
	rows, err := s.pool.Query(ctx, "SELECT "+columns+
		" FROM queue_jobs j WHERE state='parked' AND ($1='' OR uid=$1) ORDER BY created_at,job_key", tenant)
	if err != nil {
		return nil, fmt.Errorf("list parked: %w", err)
	}
	jobs, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (Job, error) { return scan(row) })
	if err != nil {
		return nil, fmt.Errorf("list parked: %w", err)
	}
	return jobs, nil
}

// signal tells this replica's dispatchers that the schedule changed: one idle dispatcher
// wakes to claim, and the watcher recomputes when the next job is due. It never blocks.
func (s *Store) signal() {
	select {
	case s.wake <- struct{}{}:
	default:
	}
	select {
	case s.rescan <- struct{}{}:
	default:
	}
}

// schedule is what the watcher needs to choose its sleep.
type schedule struct {
	// next is the earliest future due time among jobs this replica can run; zero if none.
	next time.Time
	// overdue is true when such a job is already due and was not claimed.
	overdue bool
}

// nextDue reads the schedule for the kinds this replica runs. Both halves are single index
// probes on queue_jobs_next_due.
func (s *Store) nextDue(ctx context.Context, can supported) (schedule, error) {
	var (
		next *time.Time
		out  schedule
	)
	err := s.pool.QueryRow(ctx, `SELECT
 (SELECT ready_at FROM queue_jobs WHERE ready_at > clock_timestamp() AND kind=ANY($1) ORDER BY ready_at LIMIT 1),
 EXISTS(SELECT 1 FROM queue_jobs WHERE ready_at <= clock_timestamp() AND kind=ANY($1))`, can.kinds).Scan(&next, &out.overdue)
	if err != nil {
		return schedule{}, fmt.Errorf("next due: %w", err)
	}
	if next != nil {
		out.next = *next
	}
	return out, nil
}

// Redrive returns a parked job to its schedule with its attempt counters reset. The
// lifetime budget-requeue count and the checkpoint are kept. A job parked while
// reconciling keeps its intent, so it resumes the reconciliation.
func (s *Store) Redrive(ctx context.Context, key string) error {
	j, err := s.Get(ctx, key)
	if err != nil {
		return err
	}
	return s.Tenant(ctx, j.Tenant, func(sc *Scope) error {
		return sc.Redrive(ctx, key, j.Token)
	})
}

// Redrive returns exactly the parked epoch of a job belonging to this tenant to
// its schedule. A newer terminal attempt cannot be reopened by an older command.
func (sc *Scope) Redrive(ctx context.Context, key string, expectedEpoch int64) error {
	tag, err := sc.conn.Exec(ctx, `UPDATE queue_jobs SET
state=CASE WHEN gated AND NOT initializing AND intent IS NULL THEN 'blocked' ELSE 'ready' END,
ready_at=clock_timestamp()+CASE WHEN gated AND NOT initializing AND intent IS NULL
  THEN $2*interval '1 microsecond' ELSE interval '0' END,
blocked_since=CASE WHEN gated AND NOT initializing AND intent IS NULL THEN clock_timestamp() END,
run_at=clock_timestamp(),attempts=0,deterministic_attempts=0,reconcile_attempts=0,
reason=NULL,outcome=NULL,updated_at=clock_timestamp()
WHERE job_key=$1 AND state='parked' AND uid=$3 AND lease_token=$4`, key, sc.store.cfg.GateTimeout.Microseconds(), sc.tenant, expectedEpoch)
	if err != nil {
		return fmt.Errorf("redrive: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrState
	}
	sc.store.signal()
	return nil
}

// Stats returns the number of jobs in each state and the age in seconds of the oldest job
// that is not terminal.
func (s *Store) Stats(ctx context.Context) (map[State]int64, float64, error) {
	rows, err := s.pool.Query(ctx, `SELECT state,count(*),
COALESCE(max(extract(epoch FROM clock_timestamp()-created_at)) FILTER (WHERE outcome IS NULL),0)::float8
FROM queue_jobs GROUP BY state`)
	if err != nil {
		return nil, 0, fmt.Errorf("stats: %w", err)
	}
	defer rows.Close()
	counts := make(map[State]int64)
	var oldest float64
	for rows.Next() {
		var (
			state State
			count int64
			age   float64
		)
		if err := rows.Scan(&state, &count, &age); err != nil {
			return nil, 0, fmt.Errorf("stats: %w", err)
		}
		counts[state] = count
		oldest = max(oldest, age)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("stats: %w", err)
	}
	return counts, oldest, nil
}

// Stranded reports due jobs whose kind or format this binary did not declare. During a
// rolling deployment a small number is normal on the old replicas. A number that stays above
// zero on every replica means jobs nobody runs. It returns the count and the seconds the
// oldest has been due.
//
// A replica that runs workers reports Workers.Stranded instead: it also counts declared
// kinds this replica has no handler for.
func (s *Store) Stranded(ctx context.Context) (int64, float64, error) {
	return s.stranded(ctx, s.kinds.pairs(s.kinds.names()))
}

func (s *Store) stranded(ctx context.Context, can supported) (int64, float64, error) {
	var (
		count  int64
		oldest float64
	)
	err := s.pool.QueryRow(ctx, `SELECT count(*),
COALESCE(max(extract(epoch FROM clock_timestamp()-ready_at)),0)::float8
FROM queue_jobs WHERE ready_at <= clock_timestamp()
 AND (kind,format) NOT IN (SELECT k,f FROM unnest($1::text[],$2::int[]) AS s(k,f))`,
		can.kinds, can.formats).Scan(&count, &oldest)
	if err != nil {
		return 0, 0, fmt.Errorf("stranded: %w", err)
	}
	return count, oldest, nil
}

// silent is the Observer used when the caller passes none.
type silent struct{}

func (silent) Outcome(string, Terminal, Cause)    {}
func (silent) Retry(string, Cause)                {}
func (silent) Yield(string, Cause)                {}
func (silent) BudgetRequeue(Cause)                {}
func (silent) Step(string, string, time.Duration) {}
