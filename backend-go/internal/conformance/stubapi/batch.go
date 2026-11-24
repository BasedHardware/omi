package stubapi

import (
	"context"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/conformance/kitstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// holdDelay is how long a tenant being deleted is kept off the schedule between checks.
const holdDelay = time.Second

// BatchSpeech implements batchunit.Speech against the stub, reading the kit's inline input
// from the kit store.
type BatchSpeech struct {
	Client *Client
	Inputs *kitstore.Store
}

// Transcribe sends the operation to the stub. The request id is the operation, so the stub
// charges once however often the call is repeated.
func (s BatchSpeech) Transcribe(ctx context.Context, g queue.Guarded, req batchunit.Request) (batchunit.Transcript, error) {
	input, err := s.Inputs.Input(ctx, g, req.Source.Ref)
	if errors.Is(err, kitstore.ErrAbsent) {
		return batchunit.Transcript{}, &Fault{Result: Deterministic, Cause: CauseVendorRejected}
	}
	if err != nil {
		return batchunit.Transcript{}, err
	}
	hash := Digest(ImplementationVersion + "\x00" + input)
	text, fault := s.Client.Speech(ctx, VendorInput{
		UID: req.Owner, Subject: req.UnitID, Job: BatchKey(req.Owner, req.UnitID), Request: req.Operation,
		Input: input, Hash: hash, Version: ImplementationVersion,
	}, req.Route, req.BYOK)
	if fault != nil {
		return batchunit.Transcript{}, fault
	}
	return batchunit.Transcript{Text: text}, nil
}

// Recover reports nothing committed: the stub has no way to look an operation up without
// running it. An exhausted unit therefore parks, and a redrive repeats the operation, which
// the stub still charges once.
func (BatchSpeech) Recover(context.Context, queue.Guarded, batchunit.Request) (batchunit.Transcript, error) {
	return batchunit.Transcript{}, batchunit.ErrNotCommitted
}

// BatchResults implements batchunit.Results on the kit store.
type BatchResults struct{ Store *kitstore.Store }

// Put stores the transcription under the unit's job key.
func (r BatchResults) Put(
	ctx context.Context, g queue.Guarded, req batchunit.Request, t batchunit.Transcript,
) (batchunit.Receipt, error) {
	ref := BatchKey(req.Owner, req.UnitID)
	if err := r.Store.PutResult(ctx, g, ref, req.Operation, t.Text); err != nil {
		return batchunit.Receipt{}, err
	}
	return batchunit.Receipt{Operation: req.Operation, Result: ref}, nil
}

// BatchAccounts implements batchunit.Accounts against the stub's account service.
type BatchAccounts struct{ Client *Client }

// Admissible refuses an owner who is being deleted or whose account cannot be read.
func (a BatchAccounts) Admissible(ctx context.Context, admitting queue.Admitting, owner string) (queue.EntitlementSnapshot, error) {
	if err := admitting.Err(); err != nil {
		return queue.EntitlementSnapshot{}, err
	}
	return a.check(ctx, owner, false)
}

// Runnable holds the whole tenant while its owner is being deleted.
func (a BatchAccounts) Runnable(ctx context.Context, g queue.Guarded, owner string) error {
	if err := g.Err(); err != nil {
		return err
	}
	_, err := a.check(ctx, owner, true)
	return err
}

func (a BatchAccounts) check(ctx context.Context, owner string, hold bool) (queue.EntitlementSnapshot, error) {
	account, fault := a.Client.Account(ctx, owner)
	deleting := account.Deleting || (fault != nil && fault.Cause == CauseAccountDeleting)
	switch {
	case deleting:
		return queue.EntitlementSnapshot{}, &Fault{Result: Yielded, Cause: CauseAccountDeleting, Delay: holdDelay, HoldTenant: hold}
	case fault != nil:
		return queue.EntitlementSnapshot{}, fault
	}
	return queue.EntitlementSnapshot{ChangedAt: account.EntitlementChangedAt, Generation: account.EntitlementGeneration, Exhausted: account.AllowanceExhausted}, nil
}

// BatchObserver implements batchunit.Observer on the client's dedupe metrics.
type BatchObserver struct{ Client *Client }

// Admitted records an admission.
func (o BatchObserver) Admitted(replay bool) { o.Client.Dedupe(Admission, replay) }

// Transcribed records a transcription.
func (o BatchObserver) Transcribed(reused bool) { o.Client.Dedupe(Speech, reused) }

// BatchKey derives a unit's job key.
func BatchKey(owner, unitID string) string { return ID("batch", owner, unitID) }
