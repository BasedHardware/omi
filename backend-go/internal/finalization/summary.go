package finalization

import (
	"context"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// SummaryStore repairs due debt in the existing enrichment outbox.
type SummaryStore interface {
	RepairSummary(ctx context.Context, a queue.Admitting, ref Ref, maxAge time.Duration) (rules.SummaryAction, error)
}

// RepairSummary is the per-conversation entry point for a due-summary scan.
func (s *Service) RepairSummary(ctx context.Context, ref Ref, maxAge time.Duration) (rules.SummaryAction, error) {
	var result rules.SummaryAction
	err := s.Queue.Tenant(ctx, ref.Owner, func(sc *queue.Scope) error {
		var repairErr error
		result, repairErr = s.Summaries.RepairSummary(ctx, sc.Admitting(), ref, maxAge)
		return repairErr
	})
	return result, err
}
