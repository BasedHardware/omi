package queue

import (
	"context"

	"github.com/BasedHardware/omi/backend-go/internal/platform/fault"
)

// OpenOption configures optional local-test behavior for a Store.
type OpenOption func(*Store)

// WithFaultInjector installs a seeded fault schedule. Leave it unset outside tests.
func WithFaultInjector(injector *fault.Injector) OpenOption {
	return func(store *Store) { store.faults = injector }
}

func (s *Store) inject(point fault.Point) error {
	if s.faults == nil {
		return nil
	}
	return s.faults.Inject(point)
}

// FaultPoint lets a guarded port expose its before/after call boundary to the
// active schedule. Port names should identify the interface method, such as
// "finalization.documents.load".
func (g Guarded) FaultPoint(ctx context.Context, point fault.Point) error {
	if err := g.Err(); err != nil {
		return err
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if g.faults == nil {
		return nil
	}
	return g.faults.Inject(point)
}
