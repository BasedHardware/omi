package queue

import (
	"errors"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
)

func TestRedriveRefusesAnEarlierTerminalEpoch(t *testing.T) {
	t.Parallel()
	cfg := testConfig()
	cfg.MaxAttempts, cfg.DeterministicMax = 1, 1
	s := openStore(t, pgtest.New(t), cfg, testKinds())
	ctx := t.Context()
	enqueue(t, ctx, s, demo("job", "owner"))
	first := claim(t, ctx, s)
	apply(t, first, Fail("vendorrejected"))
	if err := s.Redrive(ctx, "job"); err != nil {
		t.Fatal(err)
	}
	second := claim(t, ctx, s)
	apply(t, second, Fail("vendorrejected"))
	err := s.Tenant(ctx, "owner", func(sc *Scope) error {
		return sc.Redrive(ctx, "job", first.job.Token)
	})
	if !errors.Is(err, ErrState) {
		t.Fatalf("earlier operator command reopened a newer attempt: %v", err)
	}
	current, err := s.Get(ctx, "job")
	if err != nil || current.State != StateParked || current.Token != second.job.Token {
		t.Fatalf("new terminal epoch changed: %+v %v", current, err)
	}
}
