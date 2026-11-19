package batchunit

import (
	"context"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Speech transcribes a unit. An implementation must charge once per (job, input): repeating
// a call for the same job and input returns the first result at no cost. Errors it returns
// should implement queue.Classified so the queue knows whether to retry.
type Speech interface {
	// Transcribe returns the transcription of input for job.
	Transcribe(ctx context.Context, job queue.Job, input string) (string, error)
}

// Accounts answers whether an owner may have work admitted.
type Accounts interface {
	// Admissible returns nil when work may be admitted for owner. Its error should implement
	// queue.Classified when the owner is being deleted or the account service is unavailable.
	Admissible(ctx context.Context, owner string) error
	// Preflight reports what the queue's preflight learned for this claim: an error when the
	// claim must stop, nil when it may proceed.
	Preflight(data any) error
}

// Observer receives the kind's events for metrics.
type Observer interface {
	// Admitted records an admission and whether it was a replay of an earlier one.
	Admitted(replay bool)
	// Transcribed records a job's transcription and whether a stored result was reused.
	Transcribed(reused bool)
}

// Keys derives a unit's globally unique job key.
type Keys func(owner, unitID string) string
