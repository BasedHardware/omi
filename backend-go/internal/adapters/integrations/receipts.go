// Package integrations sends finalized-conversation webhooks and stores their receipts.
package integrations

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strconv"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Receipts stores each delivery disposition in the owner's Firestore subtree.
type Receipts struct {
	Store *docstore.Store
}

type storedReceipt struct {
	Delivered bool `firestore:"delivered"`
}

// Read returns the terminal dispositions for a batch and checks the owner fence.
func (s Receipts) Read(ctx context.Context, g queue.Guarded, ids []integrationfanout.Receipt) (map[integrationfanout.Receipt]integrationfanout.Disposition, error) {
	refs := make([]docstore.Ref, len(ids))
	for i, id := range ids {
		ref, err := receiptRef(g.Tenant(), id)
		if err != nil {
			return nil, storeError(err)
		}
		refs[i] = ref
	}
	var dispositions map[integrationfanout.Receipt]integrationfanout.Disposition
	err := s.Store.Fenced(ctx, g, g.Tenant(), func(tx *docstore.Tx) error {
		var readErr error
		dispositions, readErr = readReceipts(tx, ids, refs)
		return readErr
	})
	return dispositions, storeError(err)
}

func readReceipts(tx *docstore.Tx, ids []integrationfanout.Receipt, refs []docstore.Ref) (map[integrationfanout.Receipt]integrationfanout.Disposition, error) {
	dispositions := make(map[integrationfanout.Receipt]integrationfanout.Disposition)
	for i, ref := range refs {
		var receipt storedReceipt
		found, err := tx.Get(ref, &receipt)
		if err != nil {
			return nil, err
		}
		if found {
			dispositions[ids[i]] = integrationfanout.Rejected
			if receipt.Delivered {
				dispositions[ids[i]] = integrationfanout.Accepted
			}
		}
	}
	return dispositions, nil
}

// Record writes the first terminal disposition and preserves it on replay.
func (s Receipts) Record(ctx context.Context, g queue.Guarded, id integrationfanout.Receipt, disposition integrationfanout.Disposition) error {
	if disposition != integrationfanout.Accepted && disposition != integrationfanout.Rejected {
		return queue.Classify(errors.New("integration: nonterminal receipt"), queue.Fail(integrationfanout.CauseInvalid))
	}
	ref, err := receiptRef(g.Tenant(), id)
	if err != nil {
		return storeError(err)
	}
	err = s.Store.Fenced(ctx, g, g.Tenant(), func(tx *docstore.Tx) error {
		var previous storedReceipt
		found, getErr := tx.Get(ref, &previous)
		if getErr != nil || found {
			return getErr
		}
		return tx.Create(ref, storedReceipt{Delivered: disposition == integrationfanout.Accepted})
	})
	return storeError(err)
}

func receiptRef(owner string, id integrationfanout.Receipt) (docstore.Ref, error) {
	if id.ConversationID == "" || id.Revision <= 0 {
		return docstore.Ref{}, docstore.ErrPath
	}
	hash := sha256.Sum256([]byte(strconv.Quote(id.ConversationID) + ":" + strconv.FormatInt(id.Revision, 10) + ":" + id.AppID))
	return docstore.Doc("users", owner, "integration_delivery_receipts", hex.EncodeToString(hash[:]))
}

func storeError(err error) error {
	switch {
	case err == nil:
		return nil
	case errors.Is(err, docstore.ErrOwnerDeleting):
		return queue.Classify(err, queue.Hold(integrationfanout.CauseDeleting, time.Minute))
	case errors.Is(err, docstore.ErrPath):
		return queue.Classify(err, queue.Fail(integrationfanout.CauseInvalid))
	case errors.Is(err, docstore.ErrExists), errors.Is(err, docstore.ErrOwnerMismatch):
		return queue.Classify(err, queue.Fail(integrationfanout.CauseStore))
	}
	if call, ok := errors.AsType[*docstore.CallError](err); ok && call.Kind == docstore.KindRejected {
		return queue.Classify(err, queue.Fail(integrationfanout.CauseStore))
	}
	return queue.Classify(err, queue.Retry(integrationfanout.CauseStore, 0))
}
