package queue

import (
	"context"
	"errors"
	"fmt"
	"math/rand/v2"
	"slices"
	"sync"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
)

const kindDemo = "demo"

func testKinds() []Kind {
	return []Kind{{Name: kindDemo, Formats: []int{1}, Steps: []string{"start", "late"}, Causes: testCauses()}}
}

func testConfig() Config {
	return Config{
		Lease: time.Minute, Workers: 8, MaxAttempts: 3, DeterministicMax: 2, ReconcileMax: 3,
		GateTimeout: time.Hour, GateAbandoned: testGateAbandoned, Backoff: time.Second, BudgetDelay: time.Hour,
	}
}

// openStore opens a store on url with its schema applied.
func openStore(t *testing.T, url string, cfg Config, kinds []Kind) *Store {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	t.Cleanup(cancel)
	s, err := Open(ctx, url, cfg, kinds, nil, clock.System{})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(s.Close)
	if err := s.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	return s
}

// testStore gives the test its own database, so tests share no rows and no advisory locks.
func testStore(t *testing.T) (context.Context, *Store) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	t.Cleanup(cancel)
	return ctx, openStore(t, pgtest.New(t), testConfig(), testKinds())
}

// demo returns a plain job of the test kind.
func demo(key, tenant string) NewJob {
	return NewJob{Key: key, Tenant: tenant, Kind: kindDemo, Format: 1, Step: "start"}
}

func enqueue(t *testing.T, ctx context.Context, s *Store, n NewJob) Job {
	t.Helper()
	j, err := s.Enqueue(ctx, n)
	if err != nil {
		t.Fatal(err)
	}
	return j
}

// everything is the supported set of a replica that runs every declared kind.
func everything(s *Store) supported { return s.kinds.pairs(s.kinds.names()) }

func tryClaim(ctx context.Context, s *Store) (*Run, error) {
	r, err := s.claim(ctx, claimRequest{can: everything(s)})
	if r != nil {
		r.handler = terminalHandler{}
	}
	return r, err
}

func claim(t *testing.T, ctx context.Context, s *Store) *Run {
	t.Helper()
	r, err := tryClaim(ctx, s)
	if err != nil {
		t.Fatal(err)
	}
	return r
}

// terminalHandler accepts every exhaustion, like a kind with nothing to reconcile.
type terminalHandler struct{}

func (terminalHandler) Work(context.Context, *Run) Outcome               { return Done() }
func (terminalHandler) Exhausted(context.Context, *Reconcile) Resolution { return Park() }

func apply(t *testing.T, r *Run, o Outcome) {
	t.Helper()
	if err := o.apply(t.Context(), r); err != nil {
		t.Fatal(err)
	}
}

func due(t *testing.T, ctx context.Context, s *Store, id string) {
	t.Helper()
	_, err := s.pool.Exec(ctx, `UPDATE queue_jobs SET ready_at=clock_timestamp()-interval '1 ms',
lease_until=clock_timestamp()-interval '1 ms' WHERE job_key=$1`, id)
	if err != nil {
		t.Fatal(err)
	}
}

func TestEnqueueIdempotencyProperty(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	random := rand.New(rand.NewPCG(3100, 1))
	seen := map[string]string{}
	for i := range 80 {
		id := fmt.Sprint(random.IntN(12))
		input := fmt.Sprintf("%q", fmt.Sprint(i))
		if _, exists := seen[id]; !exists {
			seen[id] = input
		}
		j := enqueue(t, ctx, s, withMeta(demo(id, "tenant"), input))
		if j.Key != id || string(j.Meta) != seen[id] {
			t.Fatalf("key %s lost its original input", id)
		}
	}
	var total int
	if err := s.pool.QueryRow(ctx, "SELECT count(*) FROM queue_jobs").Scan(&total); err != nil || total != len(seen) {
		t.Fatalf("expected %d rows, got %d (%v)", len(seen), total, err)
	}
}

func TestOrderedLaneProperty(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	random := rand.New(rand.NewPCG(3100, 2))
	const n = 40
	orderKey := "lane"
	now := time.Now().Add(-time.Minute)
	type unit struct {
		key   string
		order time.Time
	}
	var ordered []unit
	for i := range n {
		u := unit{fmt.Sprintf("%02d", i), now.Add(time.Duration(random.IntN(10)) * time.Nanosecond)}
		ordered = append(ordered, u)
	}
	for _, i := range random.Perm(n) {
		u := ordered[i]
		enqueue(t, ctx, s, inLane(demo(u.key, "tenant"), orderKey, u.order))
	}
	slices.SortFunc(ordered, func(a, b unit) int {
		if a.order.Before(b.order) {
			return -1
		}
		if a.order.After(b.order) {
			return 1
		}
		if a.key < b.key {
			return -1
		}
		if a.key > b.key {
			return 1
		}
		return 0
	})
	for _, want := range ordered {
		r := claim(t, ctx, s)
		if r.job.Key != want.key {
			t.Fatalf("claimed %s, wanted %s", r.job.Key, want.key)
		}
		if _, err := tryClaim(ctx, s); !errors.Is(err, ErrAbsent) {
			t.Fatalf("successor escaped lease: %v", err)
		}
		apply(t, r, Done())
	}
}

func TestSingleLeaseProperty(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	for trial := range 10 {
		id := fmt.Sprint(trial)
		enqueue(t, ctx, s, demo(id, "tenant"))
		start := make(chan struct{})
		type result struct {
			r   *Run
			err error
		}
		claims := make(chan result, 12)
		var wg sync.WaitGroup
		for range cap(claims) {
			wg.Go(func() {
				<-start
				r, err := tryClaim(ctx, s)
				claims <- result{r, err}
			})
		}
		close(start)
		wg.Wait()
		close(claims)
		var old *Run
		for result := range claims {
			if errors.Is(result.err, ErrAbsent) {
				continue
			}
			if result.err != nil || old != nil {
				t.Fatalf("competing claim: %v", result.err)
			}
			old = result.r
		}
		if old == nil {
			t.Fatal("nobody claimed job")
		}
		due(t, ctx, s, id)
		next := claim(t, ctx, s)
		if next.job.Token <= old.job.Token || next.job.Attempts != 2 {
			t.Fatal("takeover lost fencing or attempt accounting")
		}
		if err := old.Save(ctx, "late", []byte("42")); !errors.Is(err, ErrLease) {
			t.Fatalf("stale save: %v", err)
		}
		if err := old.Guard(ctx, func(context.Context, Guarded) error { t.Error("stale effect"); return nil }); !errors.Is(err, ErrLease) {
			t.Fatalf("stale effect guard: %v", err)
		}
		apply(t, next, Done())
	}
}

func TestAttemptAccountingProperty(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	random := rand.New(rand.NewPCG(3100, 3))
	for trial := range 8 {
		id := fmt.Sprint(trial)
		enqueue(t, ctx, s, budgeted(demo(id, "tenant")))
		var consumed int
		for consumed < s.cfg.MaxAttempts {
			r := claim(t, ctx, s)
			if r.job.Attempts != consumed+1 {
				t.Fatalf("want claim %d, got %d", consumed+1, r.job.Attempts)
			}
			for range random.IntN(4) {
				apply(t, r, Yield(Cause("recordownercontention"), time.Hour))
				due(t, ctx, s, id)
				r = claim(t, ctx, s)
				if r.job.Attempts != consumed+1 {
					t.Fatalf("yield consumed an attempt: %d", r.job.Attempts)
				}
			}
			consumed++
			apply(t, r, Retry(Cause("vendorunavailable"), 0))
			if consumed < s.cfg.MaxAttempts {
				due(t, ctx, s, id)
			}
		}
		j, err := s.Get(ctx, id)
		if err != nil || j.State != StateParked || j.Outcome != nil || j.BudgetRequeues != 1 {
			t.Fatalf("budget parking: %+v %v", j, err)
		}

		due(t, ctx, s, id)
		if _, claimErr := tryClaim(ctx, s); !errors.Is(claimErr, errRescheduled) {
			t.Fatalf("due park was not redriven: %v", claimErr)
		}
		for i := 1; i <= s.cfg.DeterministicMax; i++ {
			r := claim(t, ctx, s)
			if r.job.Attempts != i || r.job.DeterministicAttempts != i-1 || r.job.BudgetRequeues != 1 {
				t.Fatalf("wrong budget after requeue: %+v", r.job)
			}
			apply(t, r, Fail(Cause("vendorrejected")))
			if i < s.cfg.DeterministicMax {
				due(t, ctx, s, id)
			}
		}
		j, err = s.Get(ctx, id)
		if err != nil || j.Outcome == nil || *j.Outcome != TerminalFailure {
			t.Fatalf("expected terminal failure, got %+v %v", j, err)
		}
		if err := s.Redrive(ctx, id); err != nil {
			t.Fatal(err)
		}
		r := claim(t, ctx, s)
		if r.job.Attempts != 1 || r.job.DeterministicAttempts != 0 || r.job.BudgetRequeues != 1 {
			t.Fatal("redrive reset the wrong counters")
		}
		apply(t, r, Done())
	}
}

func TestFairnessAndOrderedHold(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	owner := "big"
	for i := range 70 {
		enqueue(t, ctx, s, inLane(demo(fmt.Sprintf("big-%02d", i), owner), owner, time.Unix(int64(i), 0)))
	}
	head := claim(t, ctx, s)
	apply(t, head, Retry(Cause("transport"), time.Hour))
	// This unit was admitted after selecting the prior head.
	enqueue(t, ctx, s, inLane(demo("earlier", owner), owner, time.Unix(-1, 0)))
	enqueue(t, ctx, s, demo("other", "other"))
	r := claim(t, ctx, s)
	if r.job.Key != "other" {
		t.Fatalf("other tenant starved by held lane: %s", r.job.Key)
	}
	apply(t, r, Done())
	if _, err := tryClaim(ctx, s); !errors.Is(err, ErrAbsent) {
		t.Fatalf("held lane unexpectedly ready: %v", err)
	}

	due(t, ctx, s, head.job.Key)
	r = claim(t, ctx, s)
	if r.job.Key != head.job.Key {
		t.Fatal("retrying head lost lane to a late earlier unit")
	}
	apply(t, r, Fail(Cause("vendorrejected")))
	due(t, ctx, s, r.job.Key)
	r = claim(t, ctx, s)
	apply(t, r, Fail(Cause("vendorrejected")))
	r = claim(t, ctx, s)
	if r.job.Key != "earlier" {
		t.Fatalf("park did not release lane: %s", r.job.Key)
	}
}

func TestEraseBarrier(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, demo("job", "tenant"))
	r := claim(t, ctx, s)
	running, release, erased := make(chan struct{}), make(chan struct{}), make(chan struct{})
	effectResult, eraseResult := make(chan error, 1), make(chan error, 1)
	go func() {
		effectResult <- r.Guard(ctx, func(context.Context, Guarded) error { close(running); <-release; return nil })
	}()
	<-running
	go func() { eraseResult <- s.Erase(ctx, "tenant", func() error { close(erased); return nil }) }()
	select {
	case <-erased:
		t.Error("erase did not wait for a guarded operation")
	case <-time.After(30 * time.Millisecond):
	}
	close(release)
	if err := <-effectResult; err != nil {
		t.Fatal(err)
	}
	if err := <-eraseResult; err != nil {
		t.Fatal(err)
	}
	if _, err := s.Get(ctx, "job"); !errors.Is(err, ErrAbsent) {
		t.Fatalf("job survived erase: %v", err)
	}
	if _, err := s.Enqueue(ctx, demo("new", "tenant")); !errors.Is(err, ErrErased) {
		t.Fatalf("admitted erased tenant: %v", err)
	}
	if err := r.Guard(ctx, func(context.Context, Guarded) error { t.Fatal("erased run reached external operation"); return nil }); !errors.Is(err, ErrLease) {
		t.Fatalf("erased guard: %v", err)
	}
}

func TestGuardReadsLeaseAfterWaitingForErase(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, demo("job", "tenant"))
	r := claim(t, ctx, s)
	gate, remove := make(chan struct{}), make(chan struct{})
	eraseResult := make(chan error, 1)
	go func() {
		eraseResult <- s.withTenant(ctx, "tenant", true, func(sc *Scope) error {
			close(gate)
			select {
			case <-remove:
			case <-ctx.Done():
				return ctx.Err()
			}
			_, err := sc.conn.Exec(ctx, "DELETE FROM queue_tenants WHERE uid=$1", "tenant")
			return err
		})
	}()
	select {
	case <-gate:
	case err := <-eraseResult:
		t.Fatalf("exclusive gate failed: %v", err)
	}
	guardResult := make(chan error, 1)
	go func() {
		guardResult <- r.Guard(ctx, func(context.Context, Guarded) error { t.Error("outdated snapshot reached effect"); return nil })
	}()
	var waiting bool
	for deadline := time.Now().Add(time.Second); time.Now().Before(deadline) && !waiting; {
		err := s.pool.QueryRow(ctx, `SELECT EXISTS(
 SELECT 1 FROM pg_stat_activity
 WHERE wait_event='advisory' AND query LIKE 'SELECT queue_acquire_guard(%'
)`).Scan(&waiting)
		if err != nil {
			t.Error(err)
			break
		}
		if !waiting {
			time.Sleep(time.Millisecond)
		}
	}
	close(remove)
	if !waiting {
		t.Error("guard did not wait on the erasure gate")
	}
	if err := <-eraseResult; err != nil {
		t.Fatal(err)
	}
	if err := <-guardResult; !errors.Is(err, ErrLease) {
		t.Fatalf("guard after erase: %v", err)
	}
}

const testGateAbandoned Cause = "gate_abandoned"

// testCauses declares the causes these tests return, as a kind would.
func testCauses() []Cause {
	return []Cause{
		"transport", "ratelimited", "vendorunavailable", "vendorrejected", "versionconflict",
		"recordownercontention", "accountdeleting",
	}
}

func withMeta(n NewJob, meta string) NewJob {
	n.Meta = []byte(meta)
	return n
}

func inLane(n NewJob, lane string, at time.Time) NewJob {
	n.OrderKey, n.OrderAt = &lane, at
	return n
}

func budgeted(n NewJob) NewJob {
	n.BudgetAllowed = true
	return n
}

func gated(n NewJob) NewJob {
	n.Gated = true
	return n
}
