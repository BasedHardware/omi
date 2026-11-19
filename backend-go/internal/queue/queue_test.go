package queue

import (
	"context"
	"errors"
	"fmt"
	"math/rand/v2"
	"os"
	"slices"
	"sync"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
)

func testStore(t *testing.T) (context.Context, *Store) {
	t.Helper()
	db := os.Getenv("QUEUE_TEST_DATABASE_URL")
	if db == "" {
		t.Skip("set QUEUE_TEST_DATABASE_URL to a disposable Postgres database")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	s, err := Open(ctx, db, Config{
		Lease: time.Minute, Workers: 8, MaxAttempts: 3, DeterministicMax: 2,
		GateTimeout: time.Hour, GateAbandoned: testGateAbandoned, Causes: testCauses(), Backoff: time.Second, BudgetDelay: time.Hour,
	}, nil, clock.System{})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(s.Close)
	if err := s.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := s.pool.Exec(ctx, "TRUNCATE queue_tenants,queue_erasure CASCADE"); err != nil {
		t.Fatal(err)
	}
	return ctx, s
}

func enqueue(t *testing.T, ctx context.Context, s *Store, n NewJob) Job {
	t.Helper()
	j, err := s.Enqueue(ctx, n)
	if err != nil {
		t.Fatal(err)
	}
	return j
}

func claim(t *testing.T, ctx context.Context, s *Store) *Run {
	t.Helper()
	r, err := s.claim(ctx, claimRequest{})
	if err != nil {
		t.Fatal(err)
	}
	r.handler = terminalHandler{}
	return r
}

type terminalHandler struct{}

func (terminalHandler) Work(context.Context, *Run) Outcome { return Done() }
func (terminalHandler) Exhausted(_ context.Context, _ *Run, cause Cause, _ bool) Outcome {
	return Fail(cause)
}

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
	ctx, s := testStore(t)
	random := rand.New(rand.NewPCG(3100, 1))
	seen := map[string]string{}
	for i := range 80 {
		id := fmt.Sprint(random.IntN(12))
		input := fmt.Sprintf("%q", fmt.Sprint(i))
		if _, exists := seen[id]; !exists {
			seen[id] = input
		}
		j := enqueue(t, ctx, s, NewJob{Key: id, Tenant: "tenant", Kind: "demo", Step: "start", Meta: []byte(input)})
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
		enqueue(t, ctx, s, NewJob{Key: u.key, Tenant: "tenant", Kind: "demo", Step: "start", OrderKey: &orderKey, OrderAt: u.order})
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
		if r.Job.Key != want.key {
			t.Fatalf("claimed %s, wanted %s", r.Job.Key, want.key)
		}
		if _, err := s.claim(ctx, claimRequest{}); !errors.Is(err, ErrAbsent) {
			t.Fatalf("successor escaped lease: %v", err)
		}
		apply(t, r, Done())
	}
}

func TestSingleLeaseProperty(t *testing.T) {
	ctx, s := testStore(t)
	for trial := range 10 {
		id := fmt.Sprint(trial)
		enqueue(t, ctx, s, NewJob{Key: id, Tenant: "tenant", Kind: "demo", Step: "start"})
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
				r, err := s.claim(ctx, claimRequest{})
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
		if next.Job.Token <= old.Job.Token || next.Job.Attempts != 2 {
			t.Fatal("takeover lost fencing or attempt accounting")
		}
		if err := old.Save(ctx, "late", []byte("42")); !errors.Is(err, ErrLease) {
			t.Fatalf("stale save: %v", err)
		}
		if err := old.Guard(ctx, func(context.Context) error { t.Error("stale effect"); return nil }); !errors.Is(err, ErrLease) {
			t.Fatalf("stale effect guard: %v", err)
		}
		apply(t, next, Done())
	}
}

func TestAttemptAccountingProperty(t *testing.T) {
	ctx, s := testStore(t)
	random := rand.New(rand.NewPCG(3100, 3))
	for trial := range 8 {
		id := fmt.Sprint(trial)
		enqueue(t, ctx, s, NewJob{Key: id, Tenant: "tenant", Kind: "demo", Step: "start", BudgetAllowed: true})
		var consumed int
		for consumed < s.cfg.MaxAttempts {
			r := claim(t, ctx, s)
			if r.Job.Attempts != consumed+1 {
				t.Fatalf("want claim %d, got %d", consumed+1, r.Job.Attempts)
			}
			for range random.IntN(4) {
				apply(t, r, Yield(Cause("recordownercontention"), time.Hour))
				due(t, ctx, s, id)
				r = claim(t, ctx, s)
				if r.Job.Attempts != consumed+1 {
					t.Fatalf("yield consumed an attempt: %d", r.Job.Attempts)
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
		if _, claimErr := s.claim(ctx, claimRequest{}); !errors.Is(claimErr, errRescheduled) {
			t.Fatalf("due park was not redriven: %v", claimErr)
		}
		for i := 1; i <= s.cfg.DeterministicMax; i++ {
			r := claim(t, ctx, s)
			if r.Job.Attempts != i || r.Job.DeterministicAttempts != i-1 || r.Job.BudgetRequeues != 1 {
				t.Fatalf("wrong budget after requeue: %+v", r.Job)
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
		if r.Job.Attempts != 1 || r.Job.DeterministicAttempts != 0 || r.Job.BudgetRequeues != 1 {
			t.Fatal("redrive reset the wrong counters")
		}
		apply(t, r, Done())
	}
}

func TestFairnessAndOrderedHold(t *testing.T) {
	ctx, s := testStore(t)
	owner := "big"
	for i := range 70 {
		enqueue(t, ctx, s, NewJob{Key: fmt.Sprintf("big-%02d", i), Tenant: owner, Kind: "demo", Step: "start",
			OrderKey: &owner, OrderAt: time.Unix(int64(i), 0)})
	}
	head := claim(t, ctx, s)
	apply(t, head, Retry(Cause("transport"), time.Hour))
	// This unit was admitted after selecting the prior head.
	enqueue(t, ctx, s, NewJob{Key: "earlier", Tenant: owner, Kind: "demo", Step: "start",
		OrderKey: &owner, OrderAt: time.Unix(-1, 0)})
	enqueue(t, ctx, s, NewJob{Key: "other", Tenant: "other", Kind: "demo", Step: "start"})
	r := claim(t, ctx, s)
	if r.Job.Key != "other" {
		t.Fatalf("other tenant starved by held lane: %s", r.Job.Key)
	}
	apply(t, r, Done())
	if _, err := s.claim(ctx, claimRequest{}); !errors.Is(err, ErrAbsent) {
		t.Fatalf("held lane unexpectedly ready: %v", err)
	}

	due(t, ctx, s, head.Job.Key)
	r = claim(t, ctx, s)
	if r.Job.Key != head.Job.Key {
		t.Fatal("retrying head lost lane to a late earlier unit")
	}
	apply(t, r, Fail(Cause("vendorrejected")))
	due(t, ctx, s, r.Job.Key)
	r = claim(t, ctx, s)
	apply(t, r, Fail(Cause("vendorrejected")))
	r = claim(t, ctx, s)
	if r.Job.Key != "earlier" {
		t.Fatalf("park did not release lane: %s", r.Job.Key)
	}
}

func TestEraseBarrier(t *testing.T) {
	ctx, s := testStore(t)
	enqueue(t, ctx, s, NewJob{Key: "job", Tenant: "tenant", Kind: "demo", Step: "start"})
	r := claim(t, ctx, s)
	running, release, erased := make(chan struct{}), make(chan struct{}), make(chan struct{})
	effectResult, eraseResult := make(chan error, 1), make(chan error, 1)
	go func() {
		effectResult <- r.Guard(ctx, func(context.Context) error { close(running); <-release; return nil })
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
	if _, err := s.Enqueue(ctx, NewJob{Key: "new", Tenant: "tenant"}); !errors.Is(err, ErrErased) {
		t.Fatalf("admitted erased tenant: %v", err)
	}
	if err := r.Guard(ctx, func(context.Context) error { t.Fatal("erased run reached external operation"); return nil }); !errors.Is(err, ErrLease) {
		t.Fatalf("erased guard: %v", err)
	}
}

func TestGuardReadsLeaseAfterWaitingForErase(t *testing.T) {
	ctx, s := testStore(t)
	enqueue(t, ctx, s, NewJob{Key: "job", Tenant: "tenant", Kind: "demo", Step: "start"})
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
		guardResult <- r.Guard(ctx, func(context.Context) error { t.Error("outdated snapshot reached effect"); return nil })
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

// testCauses registers the causes these tests return, as a kind would.
func testCauses() []Cause {
	return []Cause{
		"transport", "ratelimited", "vendorunavailable", "vendorrejected", "versionconflict",
		"recordownercontention", "accountdeleting",
	}
}
