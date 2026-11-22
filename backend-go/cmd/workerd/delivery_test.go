package main

import (
	"context"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/integrations"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type guardedRecipient func(context.Context, queue.Guarded, integrationfanout.Delivery) (integrationfanout.Result, error)

func (f guardedRecipient) Send(ctx context.Context, g queue.Guarded, d integrationfanout.Delivery) (integrationfanout.Result, error) {
	return f(ctx, g, d)
}

func TestF14DeliveryUsesActiveFinalizationGuardAndReceipt(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	const owner = "delivery-owner"
	calls := 0
	sender := guardedRecipient(func(_ context.Context, g queue.Guarded, d integrationfanout.Delivery) (integrationfanout.Result, error) {
		calls++
		if g.Tenant() != owner || g.Err() != nil || d.IdempotencyKey != "conversation:fixture:finalization:1" {
			t.Error("delivery lost its original guard or key")
		}
		return integrationfanout.Result{Disposition: integrationfanout.Transient}, nil
	})
	port := integrationDelivery{service: integrationfanout.Service{Sender: sender, Receipts: integrations.Receipts{Store: bench.Store}}}
	guard := queue.GuardedForTest(t, owner, "fixture")
	event := finalization.IntegrationEvent{ConversationID: "fixture", Revision: 1, FanoutKey: "conversation:fixture:finalization:1"}
	targets := []finalization.Target{{AppID: "app", Enabled: true, Created: true, URL: "https://synthetic.invalid"}}
	if dropped, err := port.Deliver(t.Context(), guard, event, targets, finalization.DeliveryBudget{Attempt: 1, Epoch: 1}); dropped || err == nil {
		t.Fatalf("transient delivery spent its receipt: %v %v", dropped, err)
	}
	for range 2 {
		if dropped, err := port.Deliver(t.Context(), guard, event, targets, finalization.DeliveryBudget{Attempt: 2, Epoch: 1, Final: true}); !dropped || err != nil {
			t.Fatalf("final disposition: %v %v", dropped, err)
		}
	}
	if calls != 2 {
		t.Fatalf("expected retry and one final drop, got %d calls", calls)
	}
}
