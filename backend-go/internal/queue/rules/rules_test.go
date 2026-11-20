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
		"attempts remain":                 {rules.Budget{Attempts: 2, MaxAttempts: 5}, rules.NextWait},
		"last attempt records the intent": {rules.Budget{Attempts: 5, MaxAttempts: 5}, rules.NextExhaust},
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
	}
	for name, tc := range cases {
		if got := rules.AfterFail(tc.budget); got != tc.want {
			t.Errorf("%s: got %d, want %d", name, got, tc.want)
		}
	}
}

func TestAfterLaterBoundsReconciliation(t *testing.T) {
	t.Parallel()
	cases := map[string]struct {
		failed, limit int
		want          rules.Reconciling
	}{
		"first unfinished try waits":       {0, 3, rules.ReconcileAgain},
		"one try left":                     {1, 3, rules.ReconcileAgain},
		"the last try parks for repair":    {2, 3, rules.ReconcileRepair},
		"a limit of one never tries again": {0, 1, rules.ReconcileRepair},
		"already past the limit":           {9, 3, rules.ReconcileRepair},
	}
	for name, tc := range cases {
		if got := rules.AfterLater(tc.failed, tc.limit); got != tc.want {
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
		want    rules.Claim
	}{
		"ordinary ready job":           {rules.Claimed{Attempts: 1, MaxAttempts: 5}, rules.ClaimWork},
		"takeover with budget left":    {rules.Claimed{Leased: true, Attempts: 4, MaxAttempts: 5}, rules.ClaimWork},
		"takeover after the last died": {rules.Claimed{Leased: true, Attempts: 5, MaxAttempts: 5}, rules.ClaimLeaseExpired},
		"recorded intent is reconciled": {
			rules.Claimed{Leased: true, HasIntent: true, Attempts: 1, MaxAttempts: 5}, rules.ClaimReconcile,
		},
		"gate timed out": {rules.Claimed{Blocked: true, Gated: true, MaxAttempts: 5}, rules.ClaimGateAbandoned},
		"gate opened by a secret": {
			rules.Claimed{Blocked: true, Gated: true, HasSecret: true, MaxAttempts: 5}, rules.ClaimWork,
		},
		"gate still initializing": {
			rules.Claimed{Blocked: true, Gated: true, Initializing: true, MaxAttempts: 5}, rules.ClaimWork,
		},
		"gated takeover without the secret waits again": {
			rules.Claimed{Leased: true, Gated: true, Attempts: 1, MaxAttempts: 5}, rules.ClaimReblock,
		},
		"gated takeover after the last attempt reconciles": {
			rules.Claimed{Leased: true, Gated: true, Attempts: 5, MaxAttempts: 5}, rules.ClaimLeaseExpired,
		},
		"gated job in any other state never works without a secret": {
			rules.Claimed{Gated: true, Attempts: 0, MaxAttempts: 5}, rules.ClaimReblock,
		},
	}
	for name, tc := range cases {
		if got := rules.OnClaim(tc.claimed); got != tc.want {
			t.Errorf("%s: got %d, want %d", name, got, tc.want)
		}
	}
}

func TestOnClaimNeverWorksAGatedJobWithoutItsSecret(t *testing.T) {
	t.Parallel()
	for bits := range 1 << 4 {
		c := rules.Claimed{
			Gated: true, Leased: bits&1 != 0, Blocked: bits&2 != 0, HasIntent: bits&4 != 0,
			Attempts: bits >> 3 * 5, MaxAttempts: 5,
		}
		if got := rules.OnClaim(c); got == rules.ClaimWork {
			t.Errorf("%+v: a gated job past initialization reached work with no secret", c)
		}
	}
}

func TestIdleWaitSleepsUntilDueWithinBounds(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	floor, limit := 50*time.Millisecond, 2*time.Second
	cases := map[string]struct {
		next    time.Time
		overdue bool
		backoff time.Duration
		want    time.Duration
	}{
		"nothing scheduled":                       {time.Time{}, false, time.Second, limit},
		"a timer fires on time":                   {now.Add(300 * time.Millisecond), false, time.Second, 300 * time.Millisecond},
		"a timer far away":                        {now.Add(time.Hour), false, floor, limit},
		"a timer inside the floor":                {now.Add(time.Millisecond), false, time.Second, floor},
		"overdue work, first empty claim":         {time.Time{}, true, floor, floor},
		"overdue work, unclaimable for a while":   {time.Time{}, true, 800 * time.Millisecond, 800 * time.Millisecond},
		"overdue backoff never exceeds limit":     {time.Time{}, true, time.Hour, limit},
		"a timer sooner than the overdue backoff": {now.Add(200 * time.Millisecond), true, time.Second, 200 * time.Millisecond},
		"overdue backoff sooner than the timer":   {now.Add(time.Second), true, 100 * time.Millisecond, 100 * time.Millisecond},
	}
	for name, tc := range cases {
		if got := rules.IdleWait(now, tc.next, tc.overdue, floor, tc.backoff, limit); got != tc.want {
			t.Errorf("%s: got %v, want %v", name, got, tc.want)
		}
	}
}
