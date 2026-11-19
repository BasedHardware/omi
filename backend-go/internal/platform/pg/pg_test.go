package pg_test

import (
	"context"
	"math"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
)

func TestInt32Saturates(t *testing.T) {
	t.Parallel()
	for name, tc := range map[string]struct {
		in   int
		want int32
	}{
		"small":        {12, 12},
		"negative":     {-3, -3},
		"at the limit": {math.MaxInt32, math.MaxInt32},
		"above":        {math.MaxInt32 + 1, math.MaxInt32},
		"far below":    {math.MinInt32 - 1, math.MinInt32},
	} {
		if got := pg.Int32(tc.in); got != tc.want {
			t.Errorf("%s: got %d, want %d", name, got, tc.want)
		}
	}
}

func TestCleanupOutlivesACancelledParentButIsBounded(t *testing.T) {
	t.Parallel()
	parent, cancel := context.WithCancel(t.Context())
	cancel()
	cleanup, done := pg.Cleanup(parent, time.Minute)
	defer done()
	if cleanup.Err() != nil {
		t.Fatalf("cleanup context must not inherit cancellation: %v", cleanup.Err())
	}
	deadline, ok := cleanup.Deadline()
	if !ok || time.Until(deadline) > time.Minute {
		t.Fatalf("cleanup context must carry its own deadline, got %v (set=%v)", deadline, ok)
	}
}
