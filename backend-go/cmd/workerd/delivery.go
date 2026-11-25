package main

import (
	"context"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type integrationDelivery struct{ service integrationfanout.Service }

func (d integrationDelivery) Deliver(ctx context.Context, guard queue.Guarded, event finalization.IntegrationEvent, targets []finalization.Target, budget finalization.DeliveryBudget) (bool, error) {
	wire := integrationfanout.Event(event)
	output := make([]integrationfanout.Target, 0, len(targets))
	for _, target := range targets {
		output = append(output, integrationfanout.Target(target))
	}
	report, err := d.service.DeliverGuarded(ctx, guard, wire, output,
		integrationfanout.Budget{Number: budget.Attempt, ClaimToken: budget.Epoch, Final: budget.Final})
	return report.Dropped, err
}
