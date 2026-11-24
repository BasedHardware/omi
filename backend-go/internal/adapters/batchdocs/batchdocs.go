// Package batchdocs stores batch unit transcriptions in Firestore. It implements
// batchunit.Results, and it is the reference for an adapter that keeps tenant data:
//
//   - The write is fenced at the receiver (docstore.Fenced), so a write for an owner being
//     deleted is refused by Firestore even if the queue's guard has already been lost.
//   - It is idempotent per operation: a repeat returns the first receipt and writes nothing.
//   - The transcription is encrypted with the owner's key before it leaves the process.
//   - Every failure is classified, so the queue knows whether to retry, hold or stop.
package batchdocs

import (
	"context"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Collection is the subcollection of users/{owner} that holds the results, one document
// per unit.
const Collection = "batch_unit_results"

// The causes this adapter returns.
const (
	// CauseOwnerDeleting means the owner's deletion marker refused the write.
	CauseOwnerDeleting queue.Cause = "batch_owner_deleting"
	// CauseStoreUnavailable means Firestore could not take the write now.
	CauseStoreUnavailable queue.Cause = "batch_store_unavailable"
	// CauseStoreRejected means Firestore refused the write and will refuse it again.
	CauseStoreRejected queue.Cause = "batch_store_rejected"
	// CauseResultConflict means the unit already holds a result from a different operation.
	CauseResultConflict queue.Cause = "batch_result_conflict"
)

// Causes lists every cause this adapter returns, for the kind's declaration.
func Causes() []queue.Cause {
	return []queue.Cause{CauseOwnerDeleting, CauseStoreUnavailable, CauseStoreRejected, CauseResultConflict}
}

// holdDelay is how long an owner being deleted is kept off the schedule between checks.
const holdDelay = time.Minute

var errConflict = errors.New("batchdocs: unit already has a result from another operation")

// record is the stored document. The field names are a wire contract with every reader.
type record struct {
	Operation  string    `firestore:"operation"`
	Transcript string    `firestore:"transcript"`
	StoredAt   time.Time `firestore:"stored_at"`
}

// Results writes transcriptions to Firestore.
type Results struct {
	Docs  *docstore.Store
	Codec crypt.Codec
	Clock clock.Clock
}

// Put stores the transcription for the request's unit and returns its receipt.
func (r Results) Put(
	ctx context.Context, g queue.Guarded, req batchunit.Request, t batchunit.Transcript,
) (batchunit.Receipt, error) {
	doc, err := docstore.Doc("users", req.Owner, Collection, req.UnitID)
	if err != nil {
		return batchunit.Receipt{}, queue.Classify(err, queue.Fail(CauseStoreRejected))
	}
	sealed, err := r.Codec.Seal(req.Owner, []byte(t.Text))
	if err != nil {
		return batchunit.Receipt{}, queue.Classify(err, queue.Fail(CauseStoreRejected))
	}
	next := record{Operation: req.Operation, Transcript: sealed, StoredAt: r.Clock.Now()}
	err = r.Docs.Fenced(ctx, g, req.Owner, func(tx *docstore.Tx) error {
		var existing record
		found, getErr := tx.Get(doc, &existing)
		switch {
		case getErr != nil:
			return getErr
		case found && existing.Operation == req.Operation:
			// A repeat of the same operation: the first write stands.
			return nil
		case found:
			return errConflict
		}
		return tx.Create(doc, next)
	})
	if err != nil {
		return batchunit.Receipt{}, classify(err)
	}
	return batchunit.Receipt{Operation: req.Operation, Result: "users/" + req.Owner + "/" + Collection + "/" + req.UnitID}, nil
}

// classify says what the queue should do about a failed write.
func classify(err error) error {
	var fault *docstore.CallError
	switch {
	case errors.Is(err, queue.ErrLease), errors.Is(err, context.Canceled):
		// The claim is gone: FromError aborts on these as they are.
		return err
	case errors.Is(err, docstore.ErrOwnerDeleting):
		return queue.Classify(err, queue.Hold(CauseOwnerDeleting, holdDelay))
	case errors.Is(err, errConflict):
		return queue.Classify(err, queue.Fail(CauseResultConflict))
	case errors.Is(err, docstore.ErrExists):
		// Another writer created the document between this transaction's read and its
		// commit. The retry reads it and settles the same way a repeat does.
		return queue.Classify(err, queue.Retry(CauseStoreUnavailable, 0))
	case errors.As(err, &fault) && fault.Kind == docstore.KindTransient:
		return queue.Classify(err, queue.Retry(CauseStoreUnavailable, 0))
	default:
		return queue.Classify(err, queue.Fail(CauseStoreRejected))
	}
}
