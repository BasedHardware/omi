package rules_test

import (
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue/rules"
)

func TestBackoffDoublesFromBaseAndCapsAtThirtyTimes(t *testing.T) {
	t.Parallel()
	base := 100 * time.Millisecond
	want := []time.Duration{base, base, 2 * base, 4 * base, 8 * base, 16 * base, 30 * base, 30 * base}
	for attempts, expected := range want {
		if got := rules.Backoff(base, attempts); got != expected {
			t.Errorf("attempts=%d: got %v, want %v", attempts, got, expected)
		}
	}
	if got := rules.Backoff(base, 1_000_000); got != 30*base {
		t.Errorf("large attempt count: got %v, want cap %v", got, 30*base)
	}
}

func TestBackoffNeverDecreasesAsAttemptsGrow(t *testing.T) {
	t.Parallel()
	previous := time.Duration(0)
	for attempts := range 64 {
		got := rules.Backoff(time.Second, attempts)
		if got < previous {
			t.Fatalf("attempts=%d: %v is below the previous %v", attempts, got, previous)
		}
		previous = got
	}
}

func TestAfterRetry(t *testing.T) {
	t.Parallel()
	cases := map[string]struct {
		budget rules.Budget
		want   rules.Next
	}{
		"attempts remain":                     {rules.Budget{Attempts: 2, MaxAttempts: 5}, rules.NextWait},
		"last attempt records the intent":     {rules.Budget{Attempts: 5, MaxAttempts: 5}, rules.NextExhaust},
		"reconciling keeps retrying the sink": {rules.Budget{Attempts: 9, MaxAttempts: 5, Reconciling: true}, rules.NextWait},
	}
	for name, tc := range cases {
		if got := rules.AfterRetry(tc.budget); got != tc.want {
			t.Errorf("%s: got %d, want %d", name, got, tc.want)
		}
	}
}

func TestAfterFail(t *testing.T) {
	t.Parallel()
	cases := map[string]struct {
		budget rules.Budget
		want   rules.Next
	}{
		"deterministic budget remains": {rules.Budget{Attempts: 1, MaxAttempts: 5, DeterministicMax: 4}, rules.NextWait},
		"deterministic limit reached": {
			rules.Budget{Attempts: 4, MaxAttempts: 5, DeterministicAttempts: 3, DeterministicMax: 4}, rules.NextExhaust,
		},
		"transient limit reached first": {
			rules.Budget{Attempts: 5, MaxAttempts: 5, DeterministicAttempts: 0, DeterministicMax: 4}, rules.NextExhaust,
		},
		"reconciling parks": {rules.Budget{Attempts: 1, MaxAttempts: 5, DeterministicMax: 4, Reconciling: true}, rules.NextPark},
	}
	for name, tc := range cases {
		if got := rules.AfterFail(tc.budget); got != tc.want {
			t.Errorf("%s: got %d, want %d", name, got, tc.want)
		}
	}
}

func TestWillRequeueNeedsEveryCondition(t *testing.T) {
	t.Parallel()
	eligible := rules.Requeue{Allowed: true, Transient: true}
	if !rules.WillRequeue(eligible) {
		t.Fatal("an allowed transient platform job with no requeue spent must requeue")
	}
	for name, r := range map[string]rules.Requeue{
		"kind did not opt in":   {Transient: true},
		"deterministic cause":   {Allowed: true},
		"gated job":             {Allowed: true, Transient: true, Gated: true},
		"requeue already spent": {Allowed: true, Transient: true, Used: 1},
	} {
		if rules.WillRequeue(r) {
			t.Errorf("%s: must not requeue", name)
		}
	}
}

func TestOnClaim(t *testing.T) {
	t.Parallel()
	cases := map[string]struct {
		claimed rules.Claimed
		want    rules.Recovery
	}{
		"ordinary ready job":           {rules.Claimed{Attempts: 1, MaxAttempts: 5}, rules.RecoveryNone},
		"takeover with budget left":    {rules.Claimed{Leased: true, Attempts: 4, MaxAttempts: 5}, rules.RecoveryNone},
		"takeover after the last died": {rules.Claimed{Leased: true, Attempts: 5, MaxAttempts: 5}, rules.RecoveryLeaseExpired},
		"gate timed out":               {rules.Claimed{Blocked: true, MaxAttempts: 5}, rules.RecoveryGateAbandoned},
		"gate opened by a secret":      {rules.Claimed{Blocked: true, HasSecret: true, MaxAttempts: 5}, rules.RecoveryNone},
		"gate still initializing":      {rules.Claimed{Blocked: true, Initializing: true, MaxAttempts: 5}, rules.RecoveryNone},
	}
	for name, tc := range cases {
		if got := rules.OnClaim(tc.claimed); got != tc.want {
			t.Errorf("%s: got %d, want %d", name, got, tc.want)
		}
	}
}

func TestIdleWaitSleepsUntilDueWithinBounds(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	floor, limit := 50*time.Millisecond, 2*time.Second
	cases := map[string]struct {
		due  time.Time
		want time.Duration
	}{
		"nothing scheduled":    {time.Time{}, limit},
		"due soon":             {now.Add(300 * time.Millisecond), 300 * time.Millisecond},
		"due far away":         {now.Add(time.Hour), limit},
		"already due":          {now.Add(-time.Second), floor},
		"due inside the floor": {now.Add(time.Millisecond), floor},
	}
	for name, tc := range cases {
		if got := rules.IdleWait(now, tc.due, floor, limit); got != tc.want {
			t.Errorf("%s: got %v, want %v", name, got, tc.want)
		}
	}
}
