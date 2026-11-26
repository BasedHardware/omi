package queue

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
)

func TestEntitlementOwnerReplay(t *testing.T) {
	t.Parallel()
	ctx := t.Context()
	kinds := append(testKinds(), Kind{Name: "paid", Formats: []int{1}, Steps: []string{"start"}, PaidProcessing: true})
	url := pgtest.New(t)
	s := openStore(t, url, testConfig(), kinds)
	old := openStore(t, url, testConfig(), testKinds())
	setHold := func(owner string, gen int64) {
		t.Helper()
		if err := s.HoldCondition(ctx, owner, Entitlement, gen); err != nil {
			t.Fatal(err)
		}
	}
	setHold("owner", 1)
	now := time.Now()
	paid := func(key, owner string, order time.Time) NewJob {
		n := inLane(demo(key, owner), "lane", order)
		n.Kind = "paid"
		n.AudioDuration = 5 * time.Second
		n.CustodyDeadline = now.Add(time.Hour)
		return n
	}
	enqueue(t, ctx, s, paid("ja-provider", "owner", now))
	enqueue(t, ctx, s, paid("parakeet", "owner", now.Add(time.Second)))
	for range 10 {
		if _, err := tryClaim(ctx, s); !errors.Is(err, ErrAbsent) {
			t.Fatalf("held claim: %v", err)
		}
	}
	if n, _, err := old.Stranded(ctx); err != nil || n != 0 {
		t.Fatalf("stranded %d: %v", n, err)
	}
	enqueue(t, ctx, s, paid("owed", "funded-owner", now))
	if n, _, err := old.Stranded(ctx); err != nil || n != 1 {
		t.Fatalf("want exactly one unsupported, owed unit alongside two held units: %d, %v", n, err)
	}
	if err := s.EraseQueue(ctx, "funded-owner"); err != nil {
		t.Fatal(err)
	}
	stats, statsErr := s.Stats(ctx)
	want := CustomerWait{Owners: 1, Units: 2, AudioSeconds: 10}
	if statsErr != nil || stats.WaitingOnCustomer != want || stats.Counts[StateWaiting] != 0 || stats.OldestSeconds != 0 {
		t.Fatalf("stats %+v: %v", stats, statsErr)
	}
	enqueue(t, ctx, s, demo("deletion", "owner"))
	apply(t, claim(t, ctx, s), Done())
	byok := paid("byok", "owner", now.Add(time.Hour))
	byok.FundingExempt = true
	enqueue(t, ctx, s, byok)
	apply(t, claim(t, ctx, s), Done())
	expired := paid("expired", "owner", now)
	expired.CustodyDeadline = now.Add(-time.Second)
	enqueue(t, ctx, s, expired)
	checks := 0
	read := func(_ context.Context, proof Admitting, owner string) (EntitlementSnapshot, error) {
		checks++
		if proof.Err() != nil || owner != "owner" {
			t.Fatal("invalid safety check")
		}
		return EntitlementSnapshot{Generation: 2}, nil
	}
	for range 10 {
		if err := s.CheckEntitlements(ctx, read); err != nil {
			t.Fatal(err)
		}
	}
	if checks != 0 {
		t.Fatalf("held work triggered %d entitlement reads", checks)
	}
	if _, err := s.pool.Exec(ctx, "UPDATE queue_tenants SET entitlement_check_at=statement_timestamp() WHERE uid='owner'"); err != nil {
		t.Fatal(err)
	}
	if err := s.CheckEntitlements(ctx, read); err != nil || checks != 1 {
		t.Fatalf("expected one owner read, got %d: %v", checks, err)
	}
	if err := s.Release(ctx, "owner", Entitlement, 2); err != nil {
		t.Fatal(err)
	}
	setHold("owner", 1)
	for _, key := range []string{"ja-provider", "parakeet"} {
		r := claim(t, ctx, s)
		if r.job.Key != key || r.job.Attempts != 1 || !r.job.LateCapture {
			t.Fatalf("release: %+v", r.job)
		}
		apply(t, r, Done())
	}
	j, err := s.Get(ctx, "expired")
	if err != nil || j.Outcome == nil || *j.Outcome != TerminalExpiredUnfunded || j.Attempts != 0 {
		t.Fatalf("expired: %+v, %v", j, err)
	}
	if w, err := s.WaitingOnCustomer(ctx); err != nil || w != (CustomerWait{ExpiredUnfunded: 1}) {
		t.Fatalf("release accounting: %+v, %v", w, err)
	}
	if _, err := tryClaim(ctx, s); !errors.Is(err, ErrAbsent) {
		t.Fatalf("extra dispatch: %v", err)
	}
	if err := s.EraseQueue(ctx, "owner"); err != nil {
		t.Fatal(err)
	}
	after, afterErr := s.Stats(ctx)
	if afterErr != nil || after.WaitingOnCustomer != (CustomerWait{ExpiredUnfunded: 1}) {
		t.Fatalf("anonymous expiry count after erase: %+v %v", after, afterErr)
	}
	t.Log("2 held units, 10 dispatch and safety ticks: 0 per-unit entitlement reads; forced safety tick: 1 owner read; released: 2 first attempts")
}

func TestEraseWhileEntitlementHeld(t *testing.T) {
	t.Parallel()
	ctx := t.Context()
	s := openStore(t, pgtest.New(t), testConfig(), []Kind{{Name: kindDemo, Formats: []int{1}, Steps: []string{"start"}, PaidProcessing: true}})
	if err := s.HoldCondition(ctx, "owner", Entitlement, 1); err != nil {
		t.Fatal(err)
	}
	n := demo("held", "owner")
	n.AudioDuration = time.Second
	n.CustodyDeadline = time.Now().Add(time.Hour)
	enqueue(t, ctx, s, n)
	if err := s.EraseQueue(ctx, "owner"); err != nil {
		t.Fatal(err)
	}
	if err := s.Release(ctx, "owner", Entitlement, 2); !errors.Is(err, ErrErased) {
		t.Fatalf("release after erase: %v", err)
	}
	if _, err := s.Get(ctx, n.Key); !errors.Is(err, ErrAbsent) {
		t.Fatalf("erased unit: %v", err)
	}
}

func TestGrantRacesPaidIntakeAndExpiry(t *testing.T) {
	t.Parallel()
	ctx := t.Context()
	s := openStore(t, pgtest.New(t), testConfig(), []Kind{{Name: kindDemo, Formats: []int{1}, Steps: []string{"start"}, PaidProcessing: true}})
	if err := s.HoldCondition(ctx, "owner", Entitlement, 1); err != nil {
		t.Fatal(err)
	}
	n := inLane(demo("capture", "owner"), "lane", time.Now())
	n.AudioDuration = time.Second
	n.CustodyDeadline = time.Now().Add(-time.Second)
	enqueue(t, ctx, s, n)
	// Release alone must settle a past deadline even when the expiry sweep hasn't run.
	n.Key = "live"
	n.CustodyDeadline = time.Now().Add(time.Hour)
	start := make(chan struct{})
	results := make(chan error, 3)
	for range 2 {
		go func() { <-start; results <- s.Release(ctx, "owner", Entitlement, 2) }()
	}
	go func() { <-start; _, err := s.Enqueue(ctx, n); results <- err }()
	close(start)
	for range 3 {
		if err := <-results; err != nil {
			t.Fatal(err)
		}
	}
	expired, err := s.Get(ctx, "capture")
	if err != nil || expired.Outcome == nil || *expired.Outcome != TerminalExpiredUnfunded || expired.Ordered || expired.Attempts != 0 {
		t.Fatalf("expiry at release: %+v %v", expired, err)
	}
	r := claim(t, ctx, s)
	if r.job.Key != "live" || r.job.Attempts != 1 {
		t.Fatalf("race stranded the live intake: %+v", r.job)
	}
	apply(t, r, Done())
	if _, err := tryClaim(ctx, s); !errors.Is(err, ErrAbsent) {
		t.Fatalf("duplicate dispatch: %v", err)
	}
}

func TestTimeOnlyRollbackPreservesFundingFenceAndExpiry(t *testing.T) {
	t.Parallel()
	ctx := t.Context()
	url := pgtest.New(t)
	kinds := testKinds()
	kinds[0].PaidProcessing = true
	enabled := openStore(t, url, testConfig(), kinds)
	policy := testConfig()
	policy.TimeOnlyEntitlementHold = true
	disabled := openStore(t, url, policy, kinds)
	if err := enabled.HoldCondition(ctx, "owner", Entitlement, 10); err != nil {
		t.Fatal(err)
	}
	n := demo("before-switch", "owner")
	n.AudioDuration = time.Minute
	n.CustodyDeadline = time.Now().Add(time.Hour)
	enqueue(t, ctx, enabled, n)
	n.Key = "during-rollback"
	enqueue(t, ctx, disabled, n)
	n.Key = "past-deadline"
	n.CustodyDeadline = time.Now().Add(-time.Minute)
	enqueue(t, ctx, disabled, n)
	if err := disabled.CheckEntitlements(ctx, nil); err != nil {
		t.Fatal(err)
	}
	if w, err := disabled.WaitingOnCustomer(ctx); err != nil || w != (CustomerWait{Owners: 1, Units: 2, AudioSeconds: 120, ExpiredUnfunded: 1}) {
		t.Fatalf("rollback accounting: %+v %v", w, err)
	}
	r := claim(t, ctx, disabled)
	if r.job.timedGeneration != 10 {
		t.Fatalf("owner fence lost: %+v", r.job)
	}
	refusal := r.AuthorizeTimedFunding(ctx, EntitlementSnapshot{Generation: 10, Exhausted: true})
	if refusal == nil {
		t.Fatal("unfunded worker authorized")
	}
	apply(t, r, FromError(refusal, CauseUnknown))
	if _, err := tryClaim(ctx, disabled); !errors.Is(err, ErrAbsent) {
		t.Fatalf("tenant timer did not hold siblings: %v", err)
	}
	j, getErr := disabled.Get(ctx, r.job.Key)
	if getErr != nil || j.Reason == nil || *j.Reason != CauseAllowanceExhausted || j.Attempts != 0 {
		t.Fatalf("legacy hold did not refund the attempt: %+v %v", j, getErr)
	}
	if _, err := disabled.pool.Exec(ctx, "UPDATE queue_tenants SET check_after=statement_timestamp() WHERE uid='owner'"); err != nil {
		t.Fatal(err)
	}
	due(t, ctx, disabled, j.Key)
	for range 2 {
		next := claim(t, ctx, disabled)
		if err := next.AuthorizeTimedFunding(ctx, EntitlementSnapshot{Generation: 9}); err == nil {
			t.Fatal("stale grant authorized")
		}
		if err := next.AuthorizeTimedFunding(ctx, EntitlementSnapshot{Generation: 11}); err != nil {
			t.Fatal(err)
		}
		apply(t, next, Done())
	}
	if err := disabled.CheckEntitlements(ctx, nil); err != nil {
		t.Fatal(err)
	}
	w, err := disabled.WaitingOnCustomer(ctx)
	if err != nil || w != (CustomerWait{ExpiredUnfunded: 1}) {
		t.Fatalf("rollback drain: %+v %v", w, err)
	}
}
