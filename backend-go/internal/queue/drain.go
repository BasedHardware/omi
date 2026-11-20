package queue

import (
	"context"
	"errors"
	"fmt"
	"maps"
	"slices"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
)

// awaitShutdown closes one completion channel for every caller of Drain. Shut
// admission to the wait group before waiting, including on parent cancellation.
func (w *Workers) awaitShutdown() {
	<-w.done
	w.mu.Lock()
	w.stopping = true
	w.mu.Unlock()
	w.wg.Wait()
	close(w.finished)
}

func (w *Workers) isStopped() bool {
	select {
	case <-w.done:
		return true
	default:
		return false
	}
}

func (w *Workers) beginResume() bool {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.stopping || w.isStopped() {
		return false
	}
	w.wg.Add(1)
	return true
}

func (w *Workers) registerRun(id lease) bool {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.stopping {
		return false
	}
	if w.active == nil {
		w.active = make(map[lease]struct{})
	}
	w.active[id] = struct{}{}
	return true
}

func (w *Workers) forgetRun(id lease) {
	w.mu.Lock()
	defer w.mu.Unlock()
	delete(w.active, id)
}

// Drain stops intake and waits for handlers, including their heartbeats. If ctx
// expires it cancels handlers and returns the context cause after a bounded
// database cleanup. It does not wait for a handler that ignores cancellation.
// Start must receive a live parent during the grace period. Stop still waits
// for all handler goroutines before the caller closes their dependencies.
func (w *Workers) Drain(ctx context.Context) error {
	w.mu.Lock()
	w.stopping = true
	w.stopClaims()
	// A snapshot at cutoff includes launched handlers even if cancellation
	// makes one return Abort before cleanup starts. No later launch can win.
	if w.drainLeases == nil {
		w.drainLeases = slices.Collect(maps.Keys(w.active))
	}
	held := w.drainLeases
	w.mu.Unlock()

	var cause error
	select {
	case <-w.finished:
	case <-ctx.Done():
		cause = context.Cause(ctx)
	}
	w.stop()
	_, err := w.store.releaseClaims(ctx, held)
	return errors.Join(cause, err)
}

// Release only leases which still belong to this replica. A completed job or
// a newer token is untouched. The row, not the handler's mutable Job, tells us
// whether the next claim needs a live secret or must reconcile durable intent.
func (s *Store) releaseClaims(ctx context.Context, held []lease) (int64, error) {
	if len(held) == 0 {
		return 0, nil
	}
	keys := make([]string, len(held))
	tokens := make([]int64, len(held))
	for i, id := range held {
		keys[i], tokens[i] = id.key, id.token
	}
	cleanup, cancel := pg.Cleanup(ctx, 3*time.Second)
	defer cancel()
	tag, err := s.pool.Exec(cleanup, `UPDATE queue_jobs j SET attempts=attempts-1, lease_until=NULL, updated_at=clock_timestamp(),
state=CASE WHEN gated AND NOT initializing AND intent IS NULL THEN 'blocked' ELSE 'ready' END,
ready_at=clock_timestamp()+CASE WHEN gated AND NOT initializing AND intent IS NULL
 THEN $3*interval '1 microsecond' ELSE interval '0' END,
blocked_since=CASE WHEN gated AND NOT initializing AND intent IS NULL THEN clock_timestamp() ELSE blocked_since END
FROM unnest($1::text[],$2::bigint[]) AS held(key,token)
WHERE j.job_key=held.key AND j.lease_token=held.token AND j.state='leased' AND j.lease_until>clock_timestamp()`,
		keys, tokens, s.cfg.GateTimeout.Microseconds())
	if err != nil {
		return 0, fmt.Errorf("release claims: %w", err)
	}
	s.signal()
	return tag.RowsAffected(), nil
}
