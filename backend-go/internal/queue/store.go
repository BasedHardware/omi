package queue

import (
	"context"
	"embed"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
)

//go:embed migrations/*.sql
var migrations embed.FS

const (
	migrationLock = 6617271580795099302
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
	causes    map[Cause]struct{}
	observer  Observer
	clock     clock.Clock
	// wake tells one idle dispatcher that work may be claimable now.
	wake chan struct{}
	// rescan tells the schedule watcher that a due time changed, so it must not sleep on.
	rescan chan struct{}
}

// Open connects two bounded pools: one for work and a small one reserved for lease
// renewals, so a saturated work pool can never starve the heartbeats that keep leases alive.
func Open(ctx context.Context, url string, cfg Config, observer Observer, c clock.Clock) (*Store, error) {
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
		pool: pool, heartbeat: heartbeat, cfg: cfg, causes: causeSet(cfg), observer: observer,
		clock: c, wake: make(chan struct{}, 1), rescan: make(chan struct{}, 1),
	}
	if err := pool.Ping(ctx); err != nil {
		store.Close()
		return nil, fmt.Errorf("ping: %w", err)
	}
	return store, nil
}

func causeSet(cfg Config) map[Cause]struct{} {
	own := []Cause{CauseNone, CauseLeaseExpired, CauseKindUnregistered, CauseUnknown, cfg.GateAbandoned}
	set := make(map[Cause]struct{}, len(own)+len(cfg.Causes))
	for _, c := range own {
		set[c] = struct{}{}
	}
	for _, c := range cfg.Causes {
		set[c] = struct{}{}
	}
	return set
}

// known returns c if a kind registered it, otherwise CauseUnknown.
func (s *Store) known(c Cause) Cause {
	if _, ok := s.causes[c]; ok {
		return c
	}
	return CauseUnknown
}

// Causes lists every cause this store accepts, for metrics that must report zeros.
func (s *Store) Causes() []Cause {
	out := make([]Cause, 0, len(s.causes))
	for c := range s.causes {
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

// Migrate applies the embedded SQL files that are not yet recorded, under one lock, in one
// transaction. It is safe to run from several replicas at once.
func (s *Store) Migrate(ctx context.Context) error {
	files, err := migrations.ReadDir("migrations")
	if err != nil {
		return fmt.Errorf("read migrations: %w", err)
	}
	return pg.InTx(ctx, s.pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, "SELECT pg_advisory_xact_lock($1)", int64(migrationLock)); err != nil {
			return fmt.Errorf("migration lock: %w", err)
		}
		if _, err := tx.Exec(ctx, "CREATE TABLE IF NOT EXISTS queue_schema (version text PRIMARY KEY)"); err != nil {
			return fmt.Errorf("schema table: %w", err)
		}
		for _, file := range files {
			if err := applyMigration(ctx, tx, file.Name()); err != nil {
				return err
			}
		}
		return nil
	})
}

func applyMigration(ctx context.Context, tx pgx.Tx, name string) error {
	var applied bool
	err := tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM queue_schema WHERE version=$1)", name).Scan(&applied)
	if err != nil {
		return fmt.Errorf("check %s: %w", name, err)
	}
	if applied {
		return nil
	}
	sql, err := migrations.ReadFile("migrations/" + name)
	if err != nil {
		return fmt.Errorf("read %s: %w", name, err)
	}
	if _, err := tx.Exec(ctx, string(sql)); err != nil {
		return fmt.Errorf("apply %s: %w", name, err)
	}
	if _, err := tx.Exec(ctx, "INSERT INTO queue_schema VALUES ($1)", name); err != nil {
		return fmt.Errorf("record %s: %w", name, err)
	}
	return nil
}

// Ready reports whether every migration embedded in this binary has been applied.
func (s *Store) Ready(ctx context.Context) error {
	files, err := migrations.ReadDir("migrations")
	if err != nil {
		return fmt.Errorf("read migrations: %w", err)
	}
	versions := make([]string, len(files))
	for i, file := range files {
		versions[i] = file.Name()
	}
	var count int
	err = s.pool.QueryRow(ctx, "SELECT count(*) FROM queue_schema WHERE version=ANY($1)", versions).Scan(&count)
	if err != nil {
		return fmt.Errorf("read schema versions: %w", err)
	}
	if count != len(versions) {
		return errors.New("queue: apply all embedded migrations before starting workers")
	}
	return nil
}

// columns is the one projection of a job row. scan reads exactly these, in this order.
const columns = `j.job_key,j.uid,j.kind,j.subject,j.meta,j.checkpoint,j.gated,j.initializing,
j.state,j.step,j.attempts,j.deterministic_attempts,j.budget_allowed,j.budget_requeues,j.lease_token,
j.reason,j.outcome,j.created_at,j.updated_at,j.run_at,j.intent,j.intent_transient`

func scan(row pgx.Row) (Job, error) {
	var j Job
	err := row.Scan(&j.Key, &j.Tenant, &j.Kind, &j.Subject, &j.Meta, &j.Checkpoint, &j.Gated, &j.Initializing,
		&j.State, &j.Step, &j.Attempts, &j.DeterministicAttempts, &j.budgetAllowed, &j.BudgetRequeues, &j.Token,
		&j.Reason, &j.Outcome, &j.CreatedAt, &j.UpdatedAt, &j.RunAt, &j.intent, &j.intentTransient)
	if errors.Is(err, pgx.ErrNoRows) {
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

// nextDue returns the earliest time any job becomes claimable, or zero when none is scheduled.
func (s *Store) nextDue(ctx context.Context) (time.Time, error) {
	var due *time.Time
	err := s.pool.QueryRow(ctx, "SELECT min(ready_at) FROM queue_jobs WHERE ready_at IS NOT NULL").Scan(&due)
	if err != nil {
		return time.Time{}, fmt.Errorf("next due: %w", err)
	}
	if due == nil {
		return time.Time{}, nil
	}
	return *due, nil
}

// Redrive returns a parked job to its schedule with its attempt counters reset. The
// lifetime budget-requeue count and the checkpoint are kept.
func (s *Store) Redrive(ctx context.Context, key string) error {
	j, err := s.Get(ctx, key)
	if err != nil {
		return err
	}
	return s.Tenant(ctx, j.Tenant, func(sc *Scope) error {
		tag, err := sc.conn.Exec(ctx, `UPDATE queue_jobs SET
state=CASE WHEN gated AND NOT initializing THEN 'blocked' ELSE 'ready' END,
ready_at=clock_timestamp()+CASE WHEN gated AND NOT initializing THEN $2*interval '1 microsecond' ELSE interval '0' END,
blocked_since=CASE WHEN gated AND NOT initializing THEN clock_timestamp() END,
run_at=clock_timestamp(),attempts=0,deterministic_attempts=0,
reason=NULL,outcome=NULL,intent=NULL,intent_transient=false,updated_at=clock_timestamp()
WHERE job_key=$1 AND state='parked'`, key, s.cfg.GateTimeout.Microseconds())
		if err != nil {
			return fmt.Errorf("redrive: %w", err)
		}
		if tag.RowsAffected() == 0 {
			return ErrState
		}
		s.signal()
		return nil
	})
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

// silent is the Observer used when the caller passes none.
type silent struct{}

func (silent) Outcome(string, Terminal, Cause)    {}
func (silent) Retry(string, Cause)                {}
func (silent) Yield(string, Cause)                {}
func (silent) BudgetRequeue(Cause)                {}
func (silent) Step(string, string, time.Duration) {}
