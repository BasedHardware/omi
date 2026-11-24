package queue

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sync/atomic"
	"testing"
)

// Guarded proves that a call is running inside Run.Guard. A port method that reaches
// outside the process takes one, so the call cannot be written outside a guard. Only the
// queue can make a live one: the zero value reports ErrLease.
//
// Do not store a Guarded or pass it to another goroutine. It stops being valid when the
// guard returns, and an adapter checks Err before it commits anything.
type Guarded struct {
	open  *atomic.Bool
	lease lease
}

// Err returns nil while the guard is held and ErrLease once it has ended.
func (g Guarded) Err() error {
	if g.open == nil || !g.open.Load() {
		return ErrLease
	}
	return nil
}

// Tenant returns the tenant the guarded job belongs to.
func (g Guarded) Tenant() string { return g.lease.tenant }

// Operation returns the identity of one external operation of this job. It depends only on
// the job's key and the name, so every retry, every takeover and every later binary sends
// the same value, and the remote end can recognise a repeat and recover the first result.
//
// The derivation is part of the durable contract with every remote system. Never change
// it; a different derivation needs a new method and a new job format that selects it.
func (g Guarded) Operation(name string) string {
	sum := sha256.Sum256([]byte(g.lease.key + "\x00" + name))
	return "op_" + hex.EncodeToString(sum[:20])
}

// Guard runs fn, a call to an external system, while holding the tenant's shared erasure
// barrier and the job's lock, after confirming the lease is still held. An erase waits for
// it; a takeover cannot overlap it.
//
// The locks live on a database session. If that session dies while fn is still talking to
// the remote system, the barrier is gone before the remote write commits. So a remote
// system that keeps tenant data must also refuse a late write itself: see the erasure
// contract in the package README.
func (r *Run) Guard(ctx context.Context, fn func(context.Context, Guarded) error) (err error) {
	conn, err := r.store.pool.Acquire(ctx)
	if err != nil {
		return fmt.Errorf("acquire connection: %w", err)
	}
	defer conn.Release()
	// Registered before fn runs, so the locks are dropped even if fn panics.
	defer func() { err = errors.Join(err, unlock(ctx, conn)) }()
	var active bool
	err = conn.QueryRow(ctx, "SELECT queue_acquire_guard($1,$2,$3)", r.lease.tenant, r.lease.key, r.lease.token).Scan(&active)
	if err != nil {
		return fmt.Errorf("acquire guard: %w", err)
	}
	if !active {
		return ErrLease
	}
	open := &atomic.Bool{}
	open.Store(true)
	defer open.Store(false)
	return fn(ctx, Guarded{open: open, lease: r.lease})
}

// Admitting proves that a call is running inside Store.Tenant, under the tenant's erasure
// barrier. A port method called during admission takes one.
type Admitting struct {
	open   *atomic.Bool
	tenant string
}

// Err returns nil while the tenant scope is open and ErrState once it has ended.
func (a Admitting) Err() error {
	if a.open == nil || !a.open.Load() {
		return ErrState
	}
	return nil
}

// Tenant returns the tenant being admitted for.
func (a Admitting) Tenant() string { return a.tenant }

// GuardedForTest returns a live Guarded for an adapter's own tests, valid until the test
// ends. Production code gets one only from Run.Guard.
func GuardedForTest(tb testing.TB, tenant, key string) Guarded {
	tb.Helper()
	open := &atomic.Bool{}
	open.Store(true)
	tb.Cleanup(func() { open.Store(false) })
	return Guarded{open: open, lease: lease{tenant: tenant, key: key, token: 1}}
}

// AdmittingForTest returns a live Admitting for an adapter's own tests.
func AdmittingForTest(tb testing.TB, tenant string) Admitting {
	tb.Helper()
	open := &atomic.Bool{}
	open.Store(true)
	tb.Cleanup(func() { open.Store(false) })
	return Admitting{open: open, tenant: tenant}
}
