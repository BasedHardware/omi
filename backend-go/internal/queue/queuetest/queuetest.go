// Package queuetest runs a kind's handler on real workers against a real Postgres, for the
// kind's own tests. There is no fake queue: a handler is tested through the same claim,
// heartbeat, guard and fenced writes it gets in production.
package queuetest

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/fault"
	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	// GateAbandoned is the cause the harness policy records for a gate that timed out.
	GateAbandoned queue.Cause = "gate_abandoned"

	limit = 60 * time.Second
	poll  = 5 * time.Millisecond
)

// Policy is a queue policy with short delays, so retries and exhaustion finish in
// milliseconds. Change a field in the test that needs a different limit.
func Policy() queue.Config {
	return queue.Config{
		Lease: 5 * time.Second, Backoff: 2 * time.Millisecond, BudgetDelay: 2 * time.Millisecond,
		GateTimeout: time.Hour, GateAbandoned: GateAbandoned,
		MaxAttempts: 3, DeterministicMax: 2, ReconcileMax: 3, Workers: 4,
	}
}

// Harness is one test's queue: its own database, a store, and optionally workers.
type Harness struct {
	// Store is the queue under test.
	Store *queue.Store
	// URL is the test's database, for assertions that read rows directly.
	URL string
	// Faults is the schedule shared by every store instance across Restart.
	Faults *fault.Injector

	tb      testing.TB
	mu      sync.Mutex
	reports []error
	policy  queue.Config
	kinds   []queue.Kind
	workers []*queue.Workers
}

// Open creates the test's database and opens a migrated store declaring kinds.
func Open(tb testing.TB, policy queue.Config, kinds ...queue.Kind) *Harness {
	tb.Helper()
	return open(tb, policy, nil, kinds...)
}

// OpenScheduled creates a real-Postgres harness with a seeded fault schedule.
func OpenScheduled(tb testing.TB, policy queue.Config, schedule fault.Schedule, kinds ...queue.Kind) *Harness {
	tb.Helper()
	injector, err := fault.New(schedule)
	if err != nil {
		tb.Fatalf("fault schedule: %v", err)
	}
	return open(tb, policy, injector, kinds...)
}

func open(tb testing.TB, policy queue.Config, injector *fault.Injector, kinds ...queue.Kind) *Harness {
	tb.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), limit)
	defer cancel()
	url := pgtest.New(tb)
	var options []queue.OpenOption
	if injector != nil {
		options = append(options, queue.WithFaultInjector(injector))
	}
	store, err := queue.Open(ctx, url, policy, kinds, nil, clock.System{}, options...)
	if err != nil {
		tb.Fatalf("open queue: %v", err)
	}
	if err := store.Migrate(ctx); err != nil {
		tb.Fatalf("migrate queue: %v", err)
	}
	h := &Harness{Store: store, URL: url, Faults: injector, tb: tb, policy: policy, kinds: append([]queue.Kind(nil), kinds...)}
	tb.Cleanup(func() {
		h.Stop()
		h.Store.Close()
	})
	return h
}

// Start runs workers for handlers until the test ends.
func (h *Harness) Start(handlers map[string]queue.Handler) *queue.Workers {
	h.tb.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	workers, err := queue.Start(ctx, h.Store, handlers, func(err error) {
		h.mu.Lock()
		defer h.mu.Unlock()
		h.reports = append(h.reports, err)
	})
	if err != nil {
		cancel()
		h.tb.Fatalf("start workers: %v", err)
	}
	h.workers = append(h.workers, workers)
	h.tb.Cleanup(cancel)
	return workers
}

// Stop stops all replicas started by this harness.
func (h *Harness) Stop() {
	h.tb.Helper()
	for _, workers := range h.workers {
		workers.Stop()
	}
	h.workers = nil
}

// Restart closes the current store and reopens the same real database while
// preserving the schedule cursor, as a process restart would.
func (h *Harness) Restart() {
	h.RestartWithPolicy(h.policy)
}

// RestartWithPolicy reopens the same database under a new replica policy while
// retaining the schedule cursor.
func (h *Harness) RestartWithPolicy(policy queue.Config) {
	h.tb.Helper()
	h.Stop()
	h.Store.Close()
	h.policy = policy
	ctx, cancel := context.WithTimeout(context.Background(), limit)
	defer cancel()
	var options []queue.OpenOption
	if h.Faults != nil {
		options = append(options, queue.WithFaultInjector(h.Faults))
	}
	store, err := queue.Open(ctx, h.URL, h.policy, h.kinds, nil, clock.System{}, options...)
	if err != nil {
		h.tb.Fatalf("reopen queue after restart: %v", err)
	}
	if err := store.Migrate(ctx); err != nil {
		store.Close()
		h.tb.Fatalf("migrate queue after restart: %v", err)
	}
	h.Store = store
}

// Reports returns the errors the workers reported so far. A healthy run reports none.
func (h *Harness) Reports() []error {
	h.mu.Lock()
	defer h.mu.Unlock()
	return append([]error(nil), h.reports...)
}

// Settled waits until the job is terminal and returns it. A job parked for its budget
// requeue is not terminal: it has no outcome yet.
func (h *Harness) Settled(key string) queue.Job {
	h.tb.Helper()
	return h.Until(key, "it is terminal", func(j queue.Job) bool { return j.Outcome != nil })
}

// Until waits until the job satisfies done and returns it.
func (h *Harness) Until(key, what string, done func(queue.Job) bool) queue.Job {
	h.tb.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), limit)
	defer cancel()
	for {
		job, err := h.Store.Get(ctx, key)
		if err != nil {
			h.tb.Fatalf("read job %s: %v", key, err)
		}
		if done(job) {
			return job
		}
		select {
		case <-ctx.Done():
			h.tb.Fatalf("job %s: timed out waiting until %s; last seen %+v; reports %v", key, what, job, h.Reports())
		case <-time.After(poll):
		}
	}
}
