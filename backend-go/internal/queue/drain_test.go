package queue

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func receive[T any](t *testing.T, ctx context.Context, ch <-chan T) T {
	t.Helper()
	select {
	case v := <-ch:
		return v
	case <-ctx.Done():
		t.Fatal(context.Cause(ctx))
		var zero T
		return zero
	}
}

func TestDrainKeepsHeartbeatAndClosesAdmission(t *testing.T) {
	t.Parallel()
	ctx, s := workerStore(t)
	entered, finish := make(chan struct{}), make(chan struct{})
	w, _ := run(t, ctx, s, funcHandler{work: func(ctx context.Context, r *Run) Outcome {
		if r.Job().Key != "running" {
			t.Errorf("launched %s during drain", r.Job().Key)
			return Abort()
		}
		close(entered)
		select {
		case <-finish:
			return Done()
		case <-ctx.Done():
			return Abort()
		}
	}})
	enqueue(t, ctx, s, demo("running", "tenant"))
	receive(t, ctx, entered)
	gatedJob := gated(demo("scheduled", "tenant"))
	gatedJob.RunAt = time.Now().Add(time.Hour)
	enqueue(t, ctx, s, gatedJob)
	if err := w.Resume(ctx, "scheduled", "secret"); err != nil {
		t.Fatal(err)
	}
	result := make(chan error, 1)
	go func() { result <- w.Drain(ctx) }()
	receive(t, ctx, w.done)
	enqueue(t, ctx, s, demo("queued", "tenant"))
	if err := w.Resume(ctx, "scheduled", "secret"); !errors.Is(err, ErrStopped) {
		t.Fatalf("resume during drain: %v", err)
	}
	// A successful fenced completion after a full lease requires renewal during grace.
	<-time.After(s.cfg.Lease * 2)
	close(finish)
	if err := receive(t, ctx, result); err != nil {
		t.Fatal(err)
	}
	for key, state := range map[string]State{"running": StateCompleted, "queued": StateReady, "scheduled": StateBlocked} {
		j, err := s.Get(ctx, key)
		if err != nil || j.State != state || (key != "running" && j.Attempts != 0) {
			t.Fatalf("%s: state=%s attempts=%d err=%v", key, j.State, j.Attempts, err)
		}
	}
}

func TestDrainTimeoutReturnsWorkAndReconciliation(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t) // a minute lease, far longer than the drain
	stuck := make(chan struct{})
	entered := make(chan lease, 2)
	handler := funcHandler{
		work: func(_ context.Context, r *Run) Outcome {
			if r.Job().Key == "reconcile" {
				return Fail("vendorrejected")
			}
			entered <- r.lease
			<-stuck
			return Done()
		},
		exhausted: func(ctx context.Context, c *Reconcile) Resolution {
			if err := c.Save(ctx, "late", []byte(`"receipt"`)); err != nil {
				t.Error(err)
			}
			entered <- c.run.lease
			<-stuck
			return Park()
		},
	}
	w, _ := run(t, ctx, s, handler)
	defer close(stuck)
	for _, key := range []string{"work", "reconcile"} {
		enqueue(t, ctx, s, demo(key, key))
	}
	held := []lease{receive(t, ctx, entered), receive(t, ctx, entered)}
	grace, cancel := context.WithTimeout(ctx, 40*time.Millisecond)
	defer cancel()
	result := make(chan error, 1)
	go func() { result <- w.Drain(grace) }()
	if err := receive(t, ctx, result); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("drain of blocked handlers: %v", err)
	}
	for _, l := range held {
		if err := s.renew(ctx, l); !errors.Is(err, ErrLease) {
			t.Fatalf("%s: stale heartbeat: %v", l.key, err)
		}
	}
	var replacements []lease
	for range held {
		r := claim(t, ctx, s)
		replacements = append(replacements, r.lease)
		if r.job.Key == "work" {
			if r.job.Attempts != 2 || r.job.intent != nil {
				t.Fatalf("started work lost its charge: %+v", r.job)
			}
		} else if r.job.intent == nil || *r.job.intent != "vendorrejected" || r.job.ReconcileAttempts != 0 ||
			r.job.Step != "late" || string(r.job.Checkpoint) != `"receipt"` {
			t.Fatalf("takeover lost reconciliation state: %+v", r.job)
		}
	}
	// A delayed or repeated handback must leave a newer holder untouched.
	if err := s.expireClaims(ctx, held); err != nil {
		t.Fatal(err)
	}
	for _, l := range replacements {
		if err := s.renew(ctx, l); err != nil {
			t.Fatalf("shutdown fenced a replacement holder: %v", err)
		}
	}
}

type drainCommitKey struct{}

// Pause the marked direct claim at COMMIT, after the database has issued the token.
type drainCommitBarrier struct {
	entered     chan struct{}
	requestDone chan (<-chan struct{})
	release     chan struct{}
	once        sync.Once
}

func (b *drainCommitBarrier) TraceQueryStart(ctx context.Context, _ *pgx.Conn, q pgx.TraceQueryStartData) context.Context {
	if ctx.Value(drainCommitKey{}) == nil {
		return ctx
	}
	if q.SQL == direct {
		b.requestDone <- ctx.Done()
	}
	if q.SQL == "commit" {
		b.once.Do(func() { close(b.entered); <-b.release })
	}
	return ctx
}

func (*drainCommitBarrier) TraceQueryEnd(context.Context, *pgx.Conn, pgx.TraceQueryEndData) {}

func TestDrainRefundsResumeRacingCommit(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	b := &drainCommitBarrier{entered: make(chan struct{}), release: make(chan struct{}), requestDone: make(chan (<-chan struct{}), 1)}
	cfg := s.pool.Config()
	cfg.ConnConfig.Tracer = b
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		t.Fatal(err)
	}
	s.pool.Close()
	s.pool = pool
	enqueue(t, ctx, s, gated(demo("gate", "tenant")))
	w, _ := run(t, ctx, s, funcHandler{work: func(context.Context, *Run) Outcome {
		t.Error("launched a claim after drain started")
		return Done()
	}})
	release := sync.OnceFunc(func() { close(b.release) })
	defer release()
	resumed, drained := make(chan error, 1), make(chan error, 1)
	go func() { resumed <- w.Resume(context.WithValue(ctx, drainCommitKey{}, true), "gate", "secret") }()
	receive(t, ctx, b.entered)
	go func() { drained <- w.Drain(ctx) }()
	receive(t, ctx, receive(t, ctx, b.requestDone))
	release()
	if err = receive(t, ctx, drained); err != nil {
		t.Fatal(err)
	}
	if err = receive(t, ctx, resumed); !errors.Is(err, ErrStopped) {
		t.Fatalf("resume racing drain: %v", err)
	}
	j, err := s.Get(ctx, "gate")
	if err != nil || j.Token == 0 || j.Attempts != 0 || j.State != StateBlocked {
		t.Fatalf("committed claim must be refunded and gated: %+v, %v", j, err)
	}
}
