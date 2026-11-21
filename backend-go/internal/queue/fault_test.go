package queue

import (
	"context"
	"errors"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/platform/fault"
)

func TestGuardedPortBoundaryUsesTheSeededSchedule(t *testing.T) {
	t.Parallel()
	injector, err := fault.New(fault.Schedule{Seed: 81, Points: []fault.Point{fault.PortBefore("finalization.documents.load")}})
	if err != nil {
		t.Fatal(err)
	}
	ctx, store := testStoreWithFaults(t, injector)
	enqueue(t, ctx, store, demo("port-call", "tenant"))
	run := claim(t, ctx, store)
	err = run.Guard(ctx, func(ctx context.Context, guarded Guarded) error {
		pointErr := guarded.FaultPoint(ctx, fault.PortBefore("finalization.documents.load"))
		if !errors.Is(pointErr, fault.ErrInjected) {
			return errors.New("expected scheduled port fault")
		}
		return guarded.FaultPoint(ctx, fault.PortAfter("finalization.documents.load"))
	})
	if err != nil {
		t.Fatal(err)
	}
	if injector.Remaining() != 0 || len(injector.History()) != 1 {
		t.Fatalf("port fault state: remaining=%d history=%v", injector.Remaining(), injector.History())
	}
}
