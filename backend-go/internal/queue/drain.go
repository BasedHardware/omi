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

// Drain closes admission, including scheduled resumes, and keeps handlers and their
// heartbeats running until they finish or ctx ends. Pass a context with the desired grace
// period, and keep the Start context alive through the drain.
//
// After grace, Drain cancels the handlers and makes outstanding tokens immediately
// eligible for takeover. It allows up to three additional seconds for database cleanup
// and in-flight claims. It returns the grace context's error on timeout, joined with any
// cleanup error. A handler that ignores cancellation can outlive Drain.
func (w *Workers) Drain(ctx context.Context) error {
	w.mu.Lock()
	w.stopping = true
	w.stopClaims()
	// Freeze the identities before handlers can leave. A handler may have returned
	// Abort or encountered a database error without releasing its lease.
	held := slices.Collect(maps.Keys(w.active))
	w.mu.Unlock()

	var graceErr error
	select {
	case <-w.finished:
	case <-ctx.Done():
		graceErr = context.Cause(ctx)
	}
	w.stop()
	cleanup, cancel := pg.Cleanup(ctx, 3*time.Second)
	defer cancel()
	err := w.store.expireClaims(cleanup, held)
	select {
	case <-w.admissionsDone:
	case <-cleanup.Done():
		err = errors.Join(err, context.Cause(cleanup))
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	return errors.Join(graceErr, err, w.handbackErr)
}

// Expire only this replica's still-current claims. The row stays leased and due so
// OnClaim applies the normal crash rules (including final attempts and lost secrets).
// Changing the token fences even a heartbeat that was waiting on this update.
func (s *Store) expireClaims(ctx context.Context, held []lease) error {
	if len(held) == 0 {
		return nil
	}
	keys := make([]string, 0, len(held))
	tokens := make([]int64, 0, len(held))
	for _, l := range held {
		keys = append(keys, l.key)
		tokens = append(tokens, l.token)
	}
	_, err := s.pool.Exec(ctx, `UPDATE queue_jobs j SET lease_token=nextval('queue_lease_token'),
lease_until=clock_timestamp(),ready_at=clock_timestamp(),updated_at=clock_timestamp()
FROM unnest($1::text[],$2::bigint[]) AS held(key,token)
WHERE j.job_key=held.key AND j.lease_token=held.token AND j.state='leased'`, keys, tokens)
	if err != nil {
		return fmt.Errorf("expire drained claims: %w", err)
	}
	s.signal()
	return nil
}
