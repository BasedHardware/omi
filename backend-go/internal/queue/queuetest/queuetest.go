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

	tb      testing.TB
	mu      sync.Mutex
	reports []error
}

// Open creates the test's database and opens a migrated store declaring kinds.
func Open(tb testing.TB, policy queue.Config, kinds ...queue.Kind) *Harness {
	tb.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), limit)
	defer cancel()
	url := pgtest.New(tb)
	store, err := queue.Open(ctx, url, policy, kinds, nil, clock.System{})
	if err != nil {
		tb.Fatalf("open queue: %v", err)
	}
	tb.Cleanup(store.Close)
	if err := store.Migrate(ctx); err != nil {
		tb.Fatalf("migrate queue: %v", err)
	}
	return &Harness{Store: store, URL: url, tb: tb}
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
	h.tb.Cleanup(func() {
		workers.Stop()
		cancel()
	})
	return workers
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
