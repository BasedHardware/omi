package finalization

import (
	"context"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// EpisodeIntakeStore links an admitted sync clip to an existing episode.
type EpisodeIntakeStore interface {
	AttachEpisodeIntake(ctx context.Context, a queue.Admitting, ref Ref, written time.Time, clientEligible bool) (string, error)
}

// AttachEpisodeIntake is the sync intake entry point after a clip is persisted
// and before enrichment. The serving caller owns current client eligibility.
func (s *Service) AttachEpisodeIntake(ctx context.Context, ref Ref, written time.Time, clientEligible bool) (string, error) {
	if !clientEligible {
		return "", nil
	}
	if s.EpisodeIntake == nil || ref.Owner == "" || ref.ID == "" || written.IsZero() {
		return "", ErrInvalid
	}
	bounded, cancel := context.WithTimeout(ctx, EpisodeReconcileTimeout)
	defer cancel()
	var episode string
	err := s.Queue.Tenant(bounded, ref.Owner, func(scope *queue.Scope) error {
		var attachErr error
		episode, attachErr = s.EpisodeIntake.AttachEpisodeIntake(bounded, scope.Admitting(), ref, written, true)
		return attachErr
	})
	return episode, err
}
