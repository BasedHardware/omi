package finalization

import (
	"context"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// EpisodePort owns live-member closure and attachment under its own revision
// fences. Start is idempotent and returns true while a live member owns notes.
// Reconcile must enforce client capability, sync-memo and survivor ownership.
type EpisodePort interface {
	Start(ctx context.Context, g queue.Guarded, claim Claim, snapshot Conversation) (bool, error)
	Reconcile(ctx context.Context, g queue.Guarded, claim Claim, snapshot Conversation) error
}

// EpisodeReconcileTimeout bounds the best-effort work after fanout commits.
const EpisodeReconcileTimeout = 30 * time.Second

var errEpisodeNotes = errors.New("finalization: episode member notes still pending")

func (s *Service) startEpisode(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation) error {
	if s.Episodes == nil || snapshot.Discarded || !rules.EpisodeTrigger(claim.Intent.Trigger) {
		return nil
	}
	return run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		wait, err := s.Episodes.Start(ctx, g, claim, snapshot)
		if wait && err == nil {
			return queue.Classify(errEpisodeNotes, queue.Yield(CauseEpisodeNotes, time.Minute))
		}
		return err
	})
}

func (s *Service) reconcileEpisode(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation) {
	if s.Episodes == nil || snapshot.RecordingLayer || snapshot.UntrustedCapture ||
		!rules.EpisodeTrigger(claim.Intent.Trigger) {
		return
	}
	bounded, cancel := context.WithTimeout(ctx, EpisodeReconcileTimeout)
	defer cancel()
	if err := run.Guard(bounded, func(ctx context.Context, g queue.Guarded) error {
		return s.Episodes.Reconcile(ctx, g, claim, snapshot)
	}); err != nil {
		// Attachment is independent of the committed fanout and retried by its
		// own reconciliation. A failed attachment cannot spend a finalization attempt.
		return
	}
}
