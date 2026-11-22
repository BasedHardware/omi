package finalization

import (
	"context"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// SmartAbsorbPlan binds the approved pair to the exact stored input snapshots.
type SmartAbsorbPlan struct {
	SurvivorID                    string
	DonorWritten, SurvivorWritten time.Time
	SurvivorRevision              int64
}

// SmartAbsorbResult identifies the immutable survivor refresh obligation.
type SmartAbsorbResult struct {
	Survivor               Ref
	Revision, SyncRevision int64
	AlreadyApplied         bool
}

// SmartMergeStore commits an approved absorb and fences its refresh receipts.
type SmartMergeStore interface {
	Absorb(ctx context.Context, g queue.Guarded, claim Claim, plan SmartAbsorbPlan) (SmartAbsorbResult, error)
	ClaimRefresh(ctx context.Context, g queue.Guarded, claim Claim, result SmartAbsorbResult) error
	CheckpointRefresh(ctx context.Context, g queue.Guarded, claim Claim, result SmartAbsorbResult) error
}
