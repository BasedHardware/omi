package finalization

import (
	"context"
	"errors"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// BatchCustody registers the retained recording idempotently. CompleteCapture atomically
// stamps pending transcription or discarded completion under the same binding.
// DeleteEmpty must recheck that the archive is closed and empty before deletion.
type BatchCustody interface {
	Reserve(ctx context.Context, g queue.Guarded, claim Claim, snapshot Conversation) error
	CompleteCapture(ctx context.Context, g queue.Guarded, claim Claim, snapshot Conversation) error
	DeleteEmpty(ctx context.Context, g queue.Guarded, claim Claim, snapshot Conversation) error
}

func (s *Service) prepareBatch(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation) (bool, error) {
	switch rules.PlanBatch(snapshot.Batch, len(snapshot.Transcript) > 0, snapshot.Discarded) {
	case rules.BatchOrdinary:
		return false, nil
	case rules.BatchReserve:
		return false, s.reserveBatch(ctx, run, claim, snapshot)
	case rules.BatchWaitArchive:
		return false, queue.Classify(errors.New("finalization: batch archive remains open"), queue.Retry(CauseArchiveOpen, 0))
	case rules.BatchDeleteEmpty:
		err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
			return s.Batch.DeleteEmpty(ctx, g, claim, snapshot)
		})
		if err != nil {
			return false, err
		}
		return false, ErrStale
	case rules.BatchReserveAndComplete:
		if err := s.reserveBatch(ctx, run, claim, snapshot); err != nil {
			return false, err
		}
	case rules.BatchCompleteDiscarded:
		// Discarded batch rows own no recording obligation.
	}
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		return s.Batch.CompleteCapture(ctx, g, claim, snapshot)
	})
	return err == nil, err
}

func (s *Service) reserveBatch(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation) error {
	return run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		return s.Batch.Reserve(ctx, g, claim, snapshot)
	})
}
