package finalization

import (
	"context"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// ReplayStore owns durable sync-revision waits and validated operator redrive.
type ReplayStore interface {
	DeferSyncRevision(ctx context.Context, g queue.Guarded, claim Claim, expected int64) (time.Duration, error)
	PrepareRedrive(ctx context.Context, a queue.Admitting, intent Intent, previousEpoch int64, grants int) error
}

// ErrSourceChanged identifies a failed content compare-and-apply. The replay
// store independently checks whether the durable sync revision advanced.
var ErrSourceChanged = errors.New("finalization: source changed during processing")

func (s *Service) persistError(ctx context.Context, run *queue.Run, claim Claim, revision int64, err error) error {
	if !errors.Is(err, ErrSourceChanged) {
		return err
	}
	var delay time.Duration
	replayErr := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var storeErr error
		delay, storeErr = s.Replay.DeferSyncRevision(ctx, g, claim, revision)
		return storeErr
	})
	if replayErr != nil {
		return replayErr
	}
	return queue.Classify(err, queue.Yield(CauseChanged, delay))
}

// Redrive reopens the exact parked managed job. If SQL redrive fails after the
// Firestore transaction, repeating this operation completes the pending handoff.
func (s *Service) Redrive(ctx context.Context, intent Intent) error {
	if !intent.valid() || intent.RequiresBYOK {
		return ErrInvalid
	}
	err := s.Queue.Tenant(ctx, intent.Ref.Owner, func(scope *queue.Scope) error {
		return scope.Subject(ctx, Kind, intent.Ref.ID, func() error {
			job, err := scope.Get(ctx, intent.JobID)
			if err != nil {
				return err
			}
			existing, err := readIntent(job)
			if err != nil || job.Kind != Kind || existing != intent || job.State != queue.StateParked ||
				job.Outcome == nil || *job.Outcome != queue.TerminalFailure {
				return queue.ErrState
			}
			return s.Replay.PrepareRedrive(ctx, scope.Admitting(), intent, job.Token, job.BudgetRequeues)
		})
	})
	if err != nil {
		return err
	}
	return s.Queue.Redrive(ctx, intent.JobID)
}
