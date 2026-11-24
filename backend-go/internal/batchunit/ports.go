package batchunit

import (
	"context"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Every method here that leaves the process takes a queue.Guarded or a queue.Admitting.
// That is what makes "external calls run inside a guard" a compile error to get wrong, and
// tools/archcheck rejects a port method with a context and neither.

// Request identifies one transcription.
type Request struct {
	Route       Route
	BYOK        bool
	CaptureAt   time.Time
	LateCapture bool
	// Operation is the stable identity of the paid call, from Guarded.Operation. Every
	// retry, takeover and later binary sends the same value.
	Operation string
	Owner     string
	UnitID    string
	Source    Source
}

// Transcript is a transcription in memory, on its way from the vendor to the store that
// owns it. It is never saved in a job row or written to a log.
type Transcript struct{ Text string }

// ErrNotCommitted means the vendor has no result for the operation, or cannot say.
var ErrNotCommitted = errors.New("batchunit: no committed result for the operation")

// Speech is a paid transcription vendor.
//
// What every paid adapter must guarantee:
//   - Charged once per Request.Operation. Repeating a call with the same operation returns
//     the first result at no cost, including after a restart and from a newer binary.
//   - A committed result is recoverable by its operation alone.
//   - Errors are queue.Classified, so the queue knows whether to retry.
type Speech interface {
	// Transcribe runs the operation, or returns the result of an earlier run of it.
	Transcribe(ctx context.Context, g queue.Guarded, req Request) (Transcript, error)
	// Recover returns the result the vendor already committed for the operation and starts
	// nothing. It returns ErrNotCommitted when there is none, and also when the vendor has
	// no way to look one up: the job then parks for an operator instead of guessing.
	Recover(ctx context.Context, g queue.Guarded, req Request) (Transcript, error)
}

// Results stores transcriptions in the system that owns the owner's data.
//
// What every store of tenant data must guarantee:
//   - Idempotent per operation: storing the same operation twice leaves one result and
//     returns the same receipt.
//   - It refuses the write itself when the owner is erased or being deleted, in the same
//     atomic step as the write. The queue's guard is not enough: its locks end if the
//     database session dies while the remote write is still in flight.
type Results interface {
	// Put stores t for the request and returns its receipt.
	Put(ctx context.Context, g queue.Guarded, req Request, t Transcript) (Receipt, error)
}

// Accounts answers whether an owner's work may be admitted or run.
type Accounts interface {
	// Admissible returns nil when work may be admitted for owner.
	Admissible(ctx context.Context, a queue.Admitting, owner string) (queue.EntitlementSnapshot, error)
	// Runnable returns nil when owner's work may run now. For an owner who is being deleted
	// it returns a queue.Classified error whose outcome is queue.Hold, so nothing is paid
	// for and the owner's other units are not tried one by one.
	Runnable(ctx context.Context, g queue.Guarded, owner string) error
}

// Observer receives the kind's events for metrics. It does no I/O and must not block.
type Observer interface {
	// Admitted records an admission and whether it was a replay of an earlier one.
	Admitted(replay bool)
	// Transcribed records a job's transcription and whether a stored result was reused.
	Transcribed(reused bool)
}

// Keys derives a unit's globally unique job key.
type Keys func(owner, unitID string) string
