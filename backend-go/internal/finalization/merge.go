package finalization

import (
	"context"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// MergeRequest is an explicit request for ordered, distinct source conversations.
type MergeRequest struct {
	Owner     string
	Sources   []string
	Reprocess bool
}

// MergeJob is the durable ownership and target for an explicit merge.
type MergeJob struct {
	ID, Owner, Target string
	Sources           []string
	Generation, Epoch int64
	Phase             rules.MergePhase
	LeaseUntil        time.Time
}

// MergeRecoveryWork retains the job and target selected by the recovery claim.
type MergeRecoveryWork struct {
	Job    MergeJob
	Action rules.MergeRecovery
}

// MergeStore owns admission and the explicit merge document leases.
type MergeStore interface {
	AdmitMerge(ctx context.Context, a queue.Admitting, req MergeRequest) (MergeJob, error)
	ClaimMerge(ctx context.Context, a queue.Admitting, owner, id string, generation int64) (MergeJob, error)
	RenewMerge(ctx context.Context, a queue.Admitting, claim MergeJob, seal bool) error
	BeginMergeRecovery(ctx context.Context, a queue.Admitting, owner, id string) (MergeRecoveryWork, error)
	FinishMergeRollback(ctx context.Context, a queue.Admitting, claim MergeJob) error
}
