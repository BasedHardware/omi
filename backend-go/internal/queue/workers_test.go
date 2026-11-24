package queue

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
)

// Tests in this file run real workers: Start, the dispatchers, the heartbeat and a handler,
// against Postgres. The race detector sees the same goroutines production runs.

type funcHandler struct {
	work      func(ctx context.Context, r *Run) Outcome
	exhausted func(ctx context.Context, r *Reconcile) Resolution
}

func (h funcHandler) Work(ctx context.Context, r *Run) Outcome { return h.work(ctx, r) }

func (h funcHandler) Exhausted(ctx context.Context, r *Reconcile) Resolution {
	if h.exhausted == nil {
		return Park()
	}
	return h.exhausted(ctx, r)
}

// reports collects what workers report, for assertions after they stop.
type reports struct {
	mu   sync.Mutex
	errs []error
}

func (r *reports) add(err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.errs = append(r.errs, err)
}

func (r *reports) all() []error {
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]error(nil), r.errs...)
}

// workerStore opens a store with a short lease, so the heartbeat fires several times
// within one handler call.
func workerStore(t *testing.T) (context.Context, *Store) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	t.Cleanup(cancel)
	cfg := testConfig()
	cfg.Lease, cfg.Backoff = 600*time.Millisecond, 10*time.Millisecond
	return ctx, openStore(t, pgtest.New(t), cfg, testKinds())
}

func run(t *testing.T, ctx context.Context, s *Store, h Handler) (*Workers, *reports) {
	t.Helper()
	seen := &reports{}
	w, err := Start(ctx, s, map[string]Handler{kindDemo: h}, seen.add)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(w.Stop)
	return w, seen
}

func eventually(t *testing.T, ctx context.Context, what string, done func() bool) {
	t.Helper()
	for !done() {
		select {
		case <-ctx.Done():
			t.Fatalf("timed out waiting until %s", what)
		case <-time.After(10 * time.Millisecond):
		}
	}
}

func finished(t *testing.T, ctx context.Context, s *Store, key string) func() bool {
	t.Helper()
	return func() bool {
		j, err := s.Get(ctx, key)
		if err != nil {
			t.Fatal(err)
		}
		return j.Outcome != nil
	}
}

func TestWorkersRenewTheLeaseWhileTheHandlerSavesProgress(t *testing.T) {
	t.Parallel()
	ctx, s := workerStore(t)
	const jobs, saves = 12, 8
	handler := funcHandler{work: func(ctx context.Context, r *Run) Outcome {
		// Longer than the lease: only the heartbeat keeps this claim alive. Each pass reads
		// the job and saves, while the heartbeat goroutine renews concurrently.
		for i := range saves {
			progress, err := json.Marshal(map[string]int{"pass": i, "attempt": r.Job().Attempts})
			if err != nil {
				return Fail("vendorrejected")
			}
			if err := r.Save(ctx, "late", progress); err != nil {
				return FromError(err, "transport")
			}
			select {
			case <-time.After(s.cfg.Lease / 5):
			case <-ctx.Done():
				return Abort()
			}
		}
		return Done()
	}}
	_, seen := run(t, ctx, s, handler)
	for i := range jobs {
		enqueue(t, ctx, s, demo(fmt.Sprint(i), fmt.Sprint("tenant-", i%3)))
	}
	for i := range jobs {
		key := fmt.Sprint(i)
		eventually(t, ctx, "job "+key+" finishes", finished(t, ctx, s, key))
		j, err := s.Get(ctx, key)
		if err != nil || *j.Outcome != TerminalSuccess || j.Attempts != 1 || j.Step != "late" {
			t.Errorf("job %s: %+v %v: it must finish in its first claim, kept alive by renewals", key, j, err)
		}
	}
	if errs := seen.all(); len(errs) != 0 {
		t.Errorf("unexpected reports: %v", errs)
	}
}

func TestRenewalWaitsForProgressRowLock(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithTimeout(t.Context(), 30*time.Second)
	defer cancel()
	cfg := testConfig()
	cfg.Lease = 5 * time.Second
	s := openStore(t, pgtest.New(t), cfg, testKinds())
	enqueue(t, ctx, s, demo("job", "tenant"))
	r := claim(t, ctx, s)

	// Hold the same row lock as Save, using a transaction to control when it releases.
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if rollbackErr := tx.Rollback(t.Context()); rollbackErr != nil && !errors.Is(rollbackErr, pgx.ErrTxClosed) {
			t.Errorf("rollback progress write: %v", rollbackErr)
		}
	}()
	var blocker uint32
	var originalDeadline time.Time
	err = tx.QueryRow(ctx, `UPDATE queue_jobs SET step='late', updated_at=clock_timestamp()
WHERE job_key=$1 RETURNING pg_backend_pid(), lease_until`, r.lease.key).Scan(&blocker, &originalDeadline)
	if err != nil {
		t.Fatal(err)
	}

	renewed := make(chan error, 1)
	go func() { renewed <- s.renew(ctx, r.lease) }()
	eventually(t, ctx, "renewal waits on the progress write", func() bool {
		var waiting bool
		if queryErr := s.pool.QueryRow(ctx, `SELECT EXISTS (
SELECT 1 FROM pg_stat_activity WHERE $1 = ANY(pg_blocking_pids(pid)))`, blocker).Scan(&waiting); queryErr != nil {
			t.Fatal(queryErr)
		}
		return waiting
	})
	var leaseStillValid bool
	err = tx.QueryRow(ctx, `SELECT pg_sleep(1.2), clock_timestamp() < $1`, originalDeadline).Scan(nil, &leaseStillValid)
	if err != nil {
		t.Fatal(err)
	}
	if !leaseStillValid {
		t.Fatal("the original lease expired while arranging contention")
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatal(err)
	}
	renewErr := <-renewed

	// Compete for the job once the original lease would have expired.
	eventually(t, ctx, "the original lease deadline passes", func() bool {
		var expired bool
		if err := s.pool.QueryRow(ctx, "SELECT clock_timestamp() >= $1", originalDeadline).Scan(&expired); err != nil {
			t.Fatal(err)
		}
		return expired
	})
	reclaimed, claimErr := tryClaim(ctx, s)
	if reclaimed != nil {
		t.Fatalf("job reclaimed on attempt %d after renewal returned %v", reclaimed.Job().Attempts, renewErr)
	}
	if renewErr != nil || !errors.Is(claimErr, ErrAbsent) {
		t.Fatalf("renewal: %v, competing claim: %v", renewErr, claimErr)
	}
}

func TestHandlerPanicIsRetriedAndTheReplicaKeepsRunning(t *testing.T) {
	t.Parallel()
	ctx, s := workerStore(t)
	var mu sync.Mutex
	calls := map[string]int{}
	handler := funcHandler{work: func(_ context.Context, r *Run) Outcome {
		mu.Lock()
		calls[r.Job().Key]++
		n := calls[r.Job().Key]
		mu.Unlock()
		switch {
		case r.Job().Key == "panics" && n == 1:
			panic("the handler failed in a way nobody planned for")
		case r.Job().Key == "returns-nothing" && n == 1:
			return nil
		}
		return Done()
	}}
	_, seen := run(t, ctx, s, handler)
	for _, key := range []string{"panics", "returns-nothing", "healthy"} {
		enqueue(t, ctx, s, demo(key, key))
	}
	for _, key := range []string{"panics", "returns-nothing", "healthy"} {
		eventually(t, ctx, key+" finishes", finished(t, ctx, s, key))
	}
	for key, attempts := range map[string]int{"panics": 2, "returns-nothing": 2, "healthy": 1} {
		if j, err := s.Get(ctx, key); err != nil || *j.Outcome != TerminalSuccess || j.Attempts != attempts {
			t.Errorf("%s: %+v %v, want success after %d attempt(s)", key, j, err, attempts)
		}
	}
	var panicked, empty bool
	for _, err := range seen.all() {
		panicked = panicked || errors.Is(err, errHandlerPanic)
		empty = empty || errors.Is(err, errNoOutcome)
	}
	if !panicked || !empty {
		t.Errorf("both failures must be reported once: panic=%v nil outcome=%v (%v)", panicked, empty, seen.all())
	}
}

func TestPanicInsideGuardReleasesItsLocks(t *testing.T) {
	t.Parallel()
	ctx, s := workerStore(t)
	var once sync.Once
	handler := funcHandler{work: func(ctx context.Context, r *Run) Outcome {
		err := r.Guard(ctx, func(context.Context, Guarded) error {
			once.Do(func() {
				panic("the external call failed in a way nobody planned for")
			})
			return nil
		})
		return FromError(err, "transport")
	}}
	run(t, ctx, s, handler)
	enqueue(t, ctx, s, demo("job", "tenant"))
	eventually(t, ctx, "the job finishes after its guarded call panicked once", finished(t, ctx, s, "job"))
	// A session that kept the tenant's shared lock after the panic would block this forever.
	eraseCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := s.Erase(eraseCtx, "tenant", func() error { return nil }); err != nil {
		t.Fatalf("erase after a panicking guard: %v", err)
	}
}

func TestGuardedStopsBeingValidWhenTheGuardReturns(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, demo("job", "tenant"))
	r := claim(t, ctx, s)
	var kept Guarded
	err := r.Guard(ctx, func(_ context.Context, g Guarded) error {
		kept = g
		if g.Err() != nil || g.Tenant() != "tenant" {
			t.Errorf("inside the guard: err=%v tenant=%q", g.Err(), g.Tenant())
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if !errors.Is(kept.Err(), ErrLease) {
		t.Errorf("a Guarded kept past its guard must report ErrLease, got %v", kept.Err())
	}
	if !errors.Is((Guarded{}).Err(), ErrLease) {
		t.Error("the zero Guarded must report ErrLease")
	}
	// The operation identity depends on the job and the name only: a takeover sends the same
	// value the first holder sent, and a different step sends a different one.
	want := GuardedForTest(t, "tenant", "job")
	due(t, ctx, s, "job")
	next := claim(t, ctx, s)
	err = next.Guard(ctx, func(_ context.Context, g Guarded) error {
		if g.Operation("speech") != want.Operation("speech") {
			t.Errorf("a takeover changed the operation id: %q", g.Operation("speech"))
		}
		if g.Operation("speech") == g.Operation("store") {
			t.Error("two steps share an operation id")
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestResumeAfterStopReportsStopped(t *testing.T) {
	t.Parallel()
	ctx, s := workerStore(t)
	w, _ := run(t, ctx, s, terminalHandler{})
	enqueue(t, ctx, s, gated(demo("job", "tenant")))
	w.Stop()
	if err := w.Resume(ctx, "job", "live-secret"); !errors.Is(err, ErrStopped) {
		t.Fatalf("a resume after Stop reported %v: the caller must not be told it was accepted", err)
	}
	if j, err := s.Get(ctx, "job"); err != nil || j.State != StateBlocked || j.Attempts != 0 {
		t.Fatalf("the job must still be waiting for its secret: %+v %v", j, err)
	}
}

func TestResumeRunsAGatedJobWithItsSecret(t *testing.T) {
	t.Parallel()
	ctx, s := workerStore(t)
	secrets := make(chan string, 1)
	w, _ := run(t, ctx, s, funcHandler{work: func(_ context.Context, r *Run) Outcome {
		secrets <- r.Secret()
		return Done()
	}})
	enqueue(t, ctx, s, gated(demo("job", "tenant")))
	if err := w.Resume(ctx, "job", "live-secret"); err != nil {
		t.Fatal(err)
	}
	eventually(t, ctx, "the resumed job finishes", finished(t, ctx, s, "job"))
	if got := <-secrets; got != "live-secret" {
		t.Fatalf("the handler saw secret %q", got)
	}
}

func TestStartRejectsWhatIsNotDeclared(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	report := func(error) {}
	if _, err := Start(ctx, s, map[string]Handler{"nobody": terminalHandler{}}, report); !errors.Is(err, ErrUndeclared) {
		t.Errorf("a handler for an undeclared kind: %v", err)
	}
	if _, err := Start(ctx, s, map[string]Handler{kindDemo: nil}, report); !errors.Is(err, ErrUndeclared) {
		t.Errorf("a nil handler: %v", err)
	}
	if _, err := Start(ctx, s, map[string]Handler{kindDemo: terminalHandler{}}, nil); !errors.Is(err, ErrConfig) {
		t.Errorf("no report function: %v", err)
	}
}

func TestWorkersLeaveKindsTheyHaveNoHandlerFor(t *testing.T) {
	t.Parallel()
	url := pgtest.New(t)
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	t.Cleanup(cancel)
	kinds := append(testKinds(), Kind{Name: "added", Formats: []int{1}, Steps: []string{"start"}})
	cfg := testConfig()
	cfg.Backoff = 10 * time.Millisecond
	s := openStore(t, url, cfg, kinds)
	// This replica declares both kinds but runs only one of them.
	w, _ := run(t, ctx, s, terminalHandler{})
	enqueue(t, ctx, s, NewJob{Key: "other-kind", Tenant: "tenant", Kind: "added", Format: 1, Step: "start"})
	enqueue(t, ctx, s, demo("mine", "tenant"))
	eventually(t, ctx, "the handled kind finishes", finished(t, ctx, s, "mine"))
	if j, err := s.Get(ctx, "other-kind"); err != nil || j.Attempts != 0 || j.State != StateReady {
		t.Fatalf("a kind with no handler here was claimed: %+v %v", j, err)
	}
	// The store knows the kind, so by declarations alone nothing is stranded. The workers
	// know they will never run it.
	if count, _, err := s.Stranded(ctx); err != nil || count != 0 {
		t.Fatalf("every due job has a declared kind, got %d stranded (%v)", count, err)
	}
	if count, _, err := w.Stranded(ctx); err != nil || count != 1 {
		t.Fatalf("the workers must report the 1 due job they have no handler for, got %d (%v)", count, err)
	}
}
