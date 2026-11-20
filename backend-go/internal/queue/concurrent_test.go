package queue

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
)

// Wait for the competing backend to actually reach the lock we hold.
func waitForBlockedClient(t *testing.T, ctx context.Context, s *Store, tx pgx.Tx) {
	t.Helper()
	eventually(t, ctx, "another connection waits for this transaction", func() bool {
		var waiting bool
		err := s.pool.QueryRow(ctx, `SELECT EXISTS (
 SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND $1=ANY(pg_blocking_pids(pid))
)`, int64(tx.Conn().PgConn().PID())).Scan(&waiting)
		if err != nil {
			t.Fatal(err)
		}
		return waiting
	})
}

func TestHoldPausesTenantBeforeReleasingJob(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, demo("first", "tenant"))
	r := claim(t, ctx, s)
	enqueue(t, ctx, s, demo("second", "tenant"))
	held := make(chan error, 1)
	err := pg.InTx(ctx, s.pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, "SELECT job_key FROM queue_jobs WHERE job_key=$1 FOR UPDATE", r.job.Key); err != nil {
			return err
		}
		go func() { held <- r.hold(ctx, "accountdeleting", time.Hour) }()
		waitForBlockedClient(t, ctx, s, tx)
		// Hold is now waiting to release the first job. A peer must already
		// see the tenant pause, even though the second job is due.
		if other, err := tryClaim(ctx, s); !errors.Is(err, ErrAbsent) {
			t.Errorf("peer claimed during hold: %v, %v", other, err)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := <-held; err != nil {
		t.Fatal(err)
	}
}

func TestScheduledResumeHandsBackClaimWhenStopWinsLaunch(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, gated(demo("job", "tenant")))
	workerCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	// Leave the supervisor's unbuffered channel without a receiver. This
	// holds launch at the actual handoff, after commit and before any handler.
	w := &Workers{store: s, slots: make(chan struct{}, 1), spawn: make(chan func(context.Context)),
		done: workerCtx.Done(), stop: cancel, report: func(err error) { t.Error(err) }}
	w.wg.Go(func() { w.resumeNow(workerCtx, "job", "live-secret") })
	defer w.Stop()
	eventually(t, ctx, "the scheduled resume has committed its claim", func() bool {
		j, err := s.Get(ctx, "job")
		if err != nil {
			t.Fatal(err)
		}
		return j.State == StateLeased && j.Attempts == 1
	})
	w.Stop()
	j, err := s.Get(ctx, "job")
	if err != nil || j.State != StateBlocked || j.Attempts != 0 || len(w.slots) != 0 {
		t.Fatalf("scheduled resume did not hand back its claim and slot: %+v, %v", j, err)
	}
}

func TestAdmissionSeesEraseCommittedWhileWaitingForLock(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	admitted := make(chan error, 1)
	err := pg.InTx(ctx, s.pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, "SELECT pg_advisory_xact_lock("+tenantLock+")", "tenant"); err != nil {
			return err
		}
		go func() {
			admitted <- s.Tenant(ctx, "tenant", func(*Scope) error { t.Error("admitted erased tenant"); return nil })
		}()
		waitForBlockedClient(t, ctx, s, tx)
		_, err := tx.Exec(ctx, "INSERT INTO queue_erasure(tenant_hash) VALUES ("+tenantHashSQL+")", "tenant")
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := <-admitted; !errors.Is(err, ErrErased) {
		t.Fatalf("admission after erase: %v", err)
	}
}

type countQueries struct{ calls int }

func (q *countQueries) TraceQueryStart(ctx context.Context, _ *pgx.Conn, _ pgx.TraceQueryStartData) context.Context {
	q.calls++
	return ctx
}

func (*countQueries) TraceQueryEnd(context.Context, *pgx.Conn, pgx.TraceQueryEndData) {}

func TestTenantScopeTakesTwoClientStatements(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	cfg := s.pool.Config()
	trace := &countQueries{}
	cfg.ConnConfig.Tracer = trace
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	local := &Store{pool: pool}
	if err := local.Tenant(ctx, "tenant", func(*Scope) error { return nil }); err != nil {
		t.Fatal(err)
	}
	if trace.calls != 2 {
		t.Fatalf("admission barrier and unlock took %d client statements, want 2", trace.calls)
	}
}
