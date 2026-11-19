package queue

import (
	"context"
	"errors"
	"fmt"
	"maps"
	"slices"
	"sync"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue/rules"
)

const (
	dispatchers = 4
	// An idle dispatcher sleeps at least idleFloor, doubling per empty claim up to
	// idleFloorMax, and at most idleLimit even when nothing is scheduled.
	idleFloor    = 50 * time.Millisecond
	idleFloorMax = time.Second
	idleLimit    = 2 * time.Second
	// Only one dispatcher per replica watches the schedule. The others sleep this long
	// unless woken, so an idle replica costs one dispatcher's polling, not four.
	peerIdle     = 30 * time.Second
	maxDoublings = 5
	resumeFactor = 4
	resumeFloor  = 16
	// resumeTries bounds how often a scheduled resume retries a claim put off by a busy lock.
	resumeTries = 5
)

// Workers runs jobs on one replica: a few dispatchers claim work and hand each job to its
// kind's handler, never more than Config.Workers at once.
type Workers struct {
	store    *Store
	handlers map[string]Handler
	// can is the set of jobs this replica claims: the declared formats of the kinds it has
	// a handler for. Jobs outside it are left for a replica that can run them.
	can    supported
	slots  chan struct{}
	report func(error)
	stop   context.CancelFunc
	done   <-chan struct{}
	// spawn hands work to the supervisor, the one goroutine that holds the workers' context.
	spawn chan func(context.Context)

	mu       sync.Mutex
	stopping bool
	pending  map[string]struct{}
	wg       sync.WaitGroup
}

// Start launches the dispatchers. They run until ctx is cancelled or Stop is called.
// handlers maps a declared kind's name to its handler; a replica may run a subset of the
// declared kinds. report receives errors that are not part of normal operation; it must
// not block.
func Start(ctx context.Context, store *Store, handlers map[string]Handler, report func(error)) (*Workers, error) {
	if report == nil {
		return nil, fmt.Errorf("%w: a report function is required", ErrConfig)
	}
	names := make([]string, 0, len(handlers))
	for name, handler := range handlers {
		if _, ok := store.kinds.kinds[name]; !ok || handler == nil {
			return nil, fmt.Errorf("%w: handler for kind %q", ErrUndeclared, name)
		}
		names = append(names, name)
	}
	slices.Sort(names)
	ctx, cancel := context.WithCancel(ctx)
	w := &Workers{
		// The map is copied: the caller cannot change the registry after start.
		store: store, handlers: maps.Clone(handlers), can: store.kinds.pairs(names), report: report,
		slots: make(chan struct{}, store.cfg.Workers), stop: cancel, done: ctx.Done(),
		spawn: make(chan func(context.Context)), pending: make(map[string]struct{}),
	}
	w.wg.Go(func() { w.supervise(ctx) })
	for i := range min(dispatchers, store.cfg.Workers) {
		w.wg.Go(func() { w.dispatch(ctx, i == 0) })
	}
	return w, nil
}

// supervise starts every goroutine that must outlive the request that asked for it, so each
// one runs under the workers' context and is cancelled by Stop.
func (w *Workers) supervise(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		case fn := <-w.spawn:
			w.wg.Go(func() { fn(ctx) })
		}
	}
}

// start asks the supervisor to run fn. It reports false when the workers are stopping.
func (w *Workers) start(fn func(context.Context)) bool {
	select {
	case w.spawn <- fn:
		return true
	case <-w.done:
		return false
	}
}

// Stop cancels running handlers and waits for them to return. A handler that ignores its
// context delays Stop for as long as it runs, so every adapter call needs a deadline.
func (w *Workers) Stop() {
	w.mu.Lock()
	w.stopping = true
	w.stop()
	w.mu.Unlock()
	w.wg.Wait()
}

// take reserves a run slot. It returns ErrStopped when the workers are shutting down and
// the caller's own error when its context ends first.
func (w *Workers) take(ctx context.Context) error {
	// Checked first on its own: a select with several ready cases picks one at random, and
	// a free slot must never win over a stop that has already begun.
	select {
	case <-w.done:
		return ErrStopped
	default:
	}
	select {
	case w.slots <- struct{}{}:
		return nil
	case <-ctx.Done():
		return context.Cause(ctx)
	case <-w.done:
		return ErrStopped
	}
}

func (w *Workers) release() { <-w.slots }

// launch runs r in the slot the caller reserved. It reports false, without running and
// without releasing the slot, once Stop has begun.
func (w *Workers) launch(r *Run) bool {
	// The claim selected only kinds this replica has a handler for.
	handler := w.handlers[r.job.Kind]
	return w.start(func(ctx context.Context) {
		defer w.release()
		r.execute(ctx, handler, w.report)
	})
}

// Resume runs a blocked gated job with the caller's secret. If the job is scheduled for
// later, the secret is kept in memory on this replica until then; a restart loses it and the
// job stays blocked for the next caller. A nil error means the job was accepted; ErrStopped
// means the workers are shutting down and nothing was accepted.
func (w *Workers) Resume(ctx context.Context, key, secret string) error {
	if secret == "" {
		return ErrState
	}
	if err := w.take(ctx); err != nil {
		return err
	}
	r, err := w.store.claim(ctx, claimRequest{key: key, secret: secret, can: w.can})
	if err != nil {
		w.release()
		if later, ok := errors.AsType[*notDueError](err); ok {
			return w.resumeAt(key, secret, later.at)
		}
		return err
	}
	if !w.launch(r) {
		w.release()
		// Stop began between the claim and the launch: hand the claim back, so the caller
		// is not told "stopped" about a job that was in fact leased and charged.
		return errors.Join(ErrStopped, r.unclaim(ctx))
	}
	return nil
}

func (w *Workers) resumeAt(key, secret string, due time.Time) error {
	if err := w.reserve(key); err != nil {
		return err
	}
	started := w.start(func(ctx context.Context) {
		defer w.forget(key)
		select {
		case <-w.store.clock.After(due.Sub(w.store.clock.Now())):
		case <-ctx.Done():
			return
		}
		w.resumeNow(ctx, key, secret)
	})
	if !started {
		w.forget(key)
		return ErrStopped
	}
	return nil
}

// reserve records a scheduled resume, bounding how many secrets a replica holds in memory.
func (w *Workers) reserve(key string) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	switch {
	case w.stopping:
		return ErrStopped
	case w.isPending(key):
		return ErrState
	case len(w.pending) >= max(resumeFloor, resumeFactor*w.store.cfg.Workers):
		return ErrCapacity
	}
	w.pending[key] = struct{}{}
	return nil
}

func (w *Workers) isPending(key string) bool {
	_, ok := w.pending[key]
	return ok
}

func (w *Workers) forget(key string) {
	w.mu.Lock()
	delete(w.pending, key)
	w.mu.Unlock()
}

// handBack returns a claim whose launch lost to Stop, so the job is not left leased with an
// attempt spent on work that never started.
func (w *Workers) handBack(ctx context.Context, r *Run) {
	if err := r.unclaim(ctx); err != nil && !errors.Is(err, ErrLease) {
		w.report(err)
	}
}

// resumeNow claims a scheduled resume when its time comes. A busy lock puts the claim off,
// so it is tried a few times; after that the secret is dropped and the job stays blocked
// for the next caller, which is the same result as a restart.
func (w *Workers) resumeNow(ctx context.Context, key, secret string) {
	for range resumeTries {
		if w.take(ctx) != nil {
			return
		}
		r, err := w.store.claim(ctx, claimRequest{key: key, secret: secret, can: w.can})
		if err == nil && w.launch(r) {
			return
		}
		w.release()
		if err == nil {
			w.handBack(ctx, r)
			return
		}
		if !errors.Is(err, ErrDeferred) {
			gone := errors.Is(err, ErrState) || errors.Is(err, ErrAbsent)
			if !gone && ctx.Err() == nil {
				w.report(err)
			}
			return
		}
		select {
		case <-w.store.clock.After(busyRetry):
		case <-ctx.Done():
			return
		}
	}
}

// dispatch claims and launches jobs until ctx ends. With nothing to claim, the watcher
// sleeps until the next job is due, a wake arrives, or idleLimit passes; the other
// dispatchers sleep until woken. Every launch wakes a peer, so a burst of due work brings
// all dispatchers in within a few claims.
func (w *Workers) dispatch(ctx context.Context, watcher bool) {
	empty := 0
	for ctx.Err() == nil && w.take(ctx) == nil {
		r, err := w.store.claim(ctx, claimRequest{can: w.can})
		if err == nil && w.launch(r) {
			empty = 0
			w.store.signal()
			continue
		}
		w.release()
		if err == nil {
			w.handBack(ctx, r)
			return
		}
		if errors.Is(err, ErrDeferred) || errors.Is(err, errRescheduled) {
			continue
		}
		if !errors.Is(err, ErrAbsent) && ctx.Err() == nil {
			w.report(err)
		}
		if w.idle(ctx, empty, watcher) {
			empty = 0
		} else {
			empty = min(empty+1, maxDoublings)
		}
	}
}

// idle sleeps and reports whether a local enqueue woke it. Work that is due but cannot be
// claimed yet (a deferred tenant, a busy lock) would otherwise be polled at the floor, so
// the floor doubles with each consecutive empty claim.
func (w *Workers) idle(ctx context.Context, empty int, watcher bool) bool {
	wait := peerIdle
	if watcher {
		due, err := w.store.nextDue(ctx, w.can)
		if err != nil && ctx.Err() == nil {
			w.report(err)
		}
		backoff := min(idleFloorMax, idleFloor<<empty)
		wait = rules.IdleWait(w.store.clock.Now(), due.next, due.overdue, idleFloor, backoff, idleLimit)
	}
	// A schedule change wakes the watcher, which must recompute its sleep; available work
	// wakes whichever dispatcher is listening.
	var rescan <-chan struct{}
	if watcher {
		rescan = w.store.rescan
	}
	select {
	case <-ctx.Done():
		return false
	case <-w.store.wake:
		return true
	case <-rescan:
		return true
	case <-w.store.clock.After(wait):
		return false
	}
}

// Stranded reports due jobs this replica will never claim: their kind has no handler here,
// or their format is not one this binary declared. It returns the count and the seconds the
// oldest has been due. See Store.Stranded for how to read the number.
func (w *Workers) Stranded(ctx context.Context) (int64, float64, error) {
	return w.store.stranded(ctx, w.can)
}
