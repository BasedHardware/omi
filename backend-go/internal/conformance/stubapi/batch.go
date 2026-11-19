package stubapi

import (
	"context"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Transcribe implements batchunit.Speech against the stub. The request id is stable per
// job and input, so the stub charges once however often the call is repeated.
func (c *Client) Transcribe(ctx context.Context, job queue.Job, input string) (string, error) {
	result, fault := c.Speech(ctx, Input(job, "speech", input))
	if fault != nil {
		return "", fault
	}
	return result, nil
}

// BatchAccounts implements batchunit.Accounts against the stub's account service.
type BatchAccounts struct{ Client *Client }

// Admissible refuses an owner who is being deleted or whose account cannot be read.
func (a BatchAccounts) Admissible(ctx context.Context, owner string) error {
	account, fault := a.Client.Account(ctx, owner)
	if fault != nil {
		return fault
	}
	if account.Deleting {
		return &Fault{Result: Yielded, Cause: CauseAccountDeleting}
	}
	return nil
}

// Preflight returns the fault the queue's preflight recorded for this claim, if any.
func (BatchAccounts) Preflight(data any) error {
	check, ok := data.(AccountCheck)
	if !ok || check.Fault == nil {
		return nil
	}
	return check.Fault
}

// BatchObserver implements batchunit.Observer on the client's dedupe metrics.
type BatchObserver struct{ Client *Client }

// Admitted records an admission.
func (o BatchObserver) Admitted(replay bool) { o.Client.Dedupe(Admission, replay) }

// Transcribed records a transcription.
func (o BatchObserver) Transcribed(reused bool) { o.Client.Dedupe(Speech, reused) }

// BatchKey derives a unit's job key.
func BatchKey(owner, unitID string) string { return ID("batch", owner, unitID) }
