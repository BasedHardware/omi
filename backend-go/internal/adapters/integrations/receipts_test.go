package integrations

import (
	"context"
	"errors"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

type receiptFailureHandler map[string]error

func (h receiptFailureHandler) Work(_ context.Context, run *queue.Run) queue.Outcome {
	return queue.FromError(h[run.Job().Key], queue.CauseNone)
}

func (receiptFailureHandler) Exhausted(context.Context, *queue.Reconcile) queue.Resolution {
	return queue.Park()
}

func TestReceiptErrorsUseDeterministicOrTransientBudget(t *testing.T) {
	t.Parallel()
	policy := queuetest.Policy()
	h := queuetest.Open(t, policy, queue.Kind{
		Name: "test_finalization", Formats: []int{1}, Steps: []string{"integrations"}, Causes: integrationfanout.Causes(),
	})
	failures := receiptFailureHandler{
		"undecodable":    malformedReceiptError(t),
		"conflict":       storeError(docstore.ErrExists),
		"owner-mismatch": storeError(docstore.ErrOwnerMismatch),
		"unavailable":    storeError(&docstore.CallError{Kind: docstore.KindTransient, Code: "Unavailable"}),
		"unclassified":   storeError(errors.New("interrupted store call")),
	}
	h.Start(map[string]queue.Handler{"test_finalization": failures})
	for key, attempts := range map[string]int{
		"undecodable": policy.DeterministicMax, "conflict": policy.DeterministicMax,
		"owner-mismatch": policy.DeterministicMax, "unavailable": policy.MaxAttempts, "unclassified": policy.MaxAttempts,
	} {
		enqueue(t, h, key, "conversation")
		job := h.Settled(key)
		if job.Outcome == nil || *job.Outcome != queue.TerminalFailure || job.Attempts != attempts ||
			job.Reason == nil || *job.Reason != integrationfanout.CauseStore {
			t.Errorf("%s: outcome %v, attempts %d, reason %v", key, job.Outcome, job.Attempts, job.Reason)
		}
	}
}

func malformedReceiptError(t *testing.T) error {
	t.Helper()
	bench := docstoretest.Open(t)
	g := queue.GuardedForTest(t, "owner", "job")
	store := Receipts{Store: bench.Store}
	id := integrationfanout.Receipt{ConversationID: "conversation", Revision: 1, AppID: "app"}
	if err := store.Record(t.Context(), g, id, integrationfanout.Accepted); err != nil {
		t.Fatal(err)
	}
	iter := bench.Raw.Collection("users").Doc("owner").Collection("integration_delivery_receipts").Documents(t.Context())
	defer iter.Stop()
	doc, err := iter.Next()
	if err != nil {
		t.Fatal(err)
	}
	if _, setErr := doc.Ref.Set(t.Context(), map[string]any{"delivered": "not-a-boolean"}); setErr != nil {
		t.Fatal(setErr)
	}
	_, err = store.Read(t.Context(), g, []integrationfanout.Receipt{id})
	if call, ok := errors.AsType[*docstore.CallError](err); !ok || call.Kind != docstore.KindRejected {
		t.Fatalf("malformed receipt error: %v", err)
	}
	return err
}
