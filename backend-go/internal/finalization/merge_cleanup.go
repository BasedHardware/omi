package finalization

import (
	"context"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// SealedMergeStore owns the correction-fenced, paid-work-free cleanup path.
type SealedMergeStore interface {
	RenewMerge(ctx context.Context, a queue.Admitting, claim MergeJob, seal bool) error
	CleanupMergeSource(ctx context.Context, a queue.Admitting, claim MergeJob, id string) error
	CompleteMergeCleanup(ctx context.Context, a queue.Admitting, claim MergeJob) error
}

// RunSealedCleanup renews the merge lease while resuming source cleanup for
// the sealed target. It joins the heartbeat before returning.
func RunSealedCleanup(ctx context.Context, q *queue.Store, store SealedMergeStore, clk clock.Clock, claim MergeJob) error {
	if claim.Phase != rules.MergeSourceCleanup || claim.Epoch <= 0 || claim.Generation <= 0 {
		return ErrInvalid
	}
	work, cancel := context.WithCancel(ctx)
	heartbeat := make(chan error, 1)
	go func() {
		heartbeat <- renewCleanup(work, q, store, clk, claim)
		cancel()
	}()
	err := cleanupSources(work, q, store, claim)
	cancel()
	renewErr := <-heartbeat
	if errors.Is(renewErr, context.Canceled) {
		renewErr = nil
	}
	return errors.Join(err, renewErr)
}

func renewCleanup(ctx context.Context, q *queue.Store, store SealedMergeStore, clk clock.Clock, claim MergeJob) error {
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-clk.After(30 * time.Second):
			err := q.Tenant(ctx, claim.Owner, func(sc *queue.Scope) error {
				return store.RenewMerge(ctx, sc.Admitting(), claim, false)
			})
			if err != nil {
				return err
			}
		}
	}
}

func cleanupSources(ctx context.Context, q *queue.Store, store SealedMergeStore, claim MergeJob) error {
	for _, id := range claim.Sources {
		err := q.Tenant(ctx, claim.Owner, func(sc *queue.Scope) error {
			return store.CleanupMergeSource(ctx, sc.Admitting(), claim, id)
		})
		if err != nil {
			return err
		}
	}
	return q.Tenant(ctx, claim.Owner, func(sc *queue.Scope) error {
		return store.CompleteMergeCleanup(ctx, sc.Admitting(), claim)
	})
}
