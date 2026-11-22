package queue

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
)

// Tests in this file each protect one contract a kind relies on without checking for it.

func TestReplicaClaimsOnlyKindsAndFormatsItDeclares(t *testing.T) {
	t.Parallel()
	url := pgtest.New(t)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	t.Cleanup(cancel)
	older := openStore(t, url, testConfig(), testKinds())
	newerKinds := []Kind{
		{Name: kindDemo, Formats: []int{1, 2}, Steps: []string{"start", "late"}, Causes: testCauses()},
		{Name: "added", Formats: []int{1}, Steps: []string{"start"}},
	}
	newer := openStore(t, url, testConfig(), newerKinds)

	// A rolling deployment: the new binary admits work the old one has never heard of.
	enqueue(t, ctx, newer, NewJob{Key: "new-kind", Tenant: "a", Kind: "added", Format: 1, Step: "start"})
	enqueue(t, ctx, newer, NewJob{Key: "new-format", Tenant: "b", Kind: kindDemo, Format: 2, Step: "start"})
	lane := "lane"
	head := inLane(NewJob{Key: "lane-head", Tenant: "c", Kind: kindDemo, Format: 2, Step: "start"}, lane, time.Unix(1, 0))
	enqueue(t, ctx, newer, head)
	enqueue(t, ctx, newer, inLane(demo("lane-next", "c"), lane, time.Unix(2, 0)))

	for range 5 {
		if r, err := tryClaim(ctx, older); !errors.Is(err, ErrAbsent) {
			t.Fatalf("the old replica claimed %+v (%v): it must leave work it cannot run", r, err)
		}
	}
	for _, key := range []string{"new-kind", "new-format", "lane-head", "lane-next"} {
		if j, err := older.Get(ctx, key); err != nil || j.Attempts != 0 || j.State != StateReady {
			t.Fatalf("%s was touched by the old replica: %+v %v", key, j, err)
		}
	}
	if count, _, err := older.Stranded(ctx); err != nil || count != 3 {
		t.Fatalf("the old replica must report the 3 due jobs it cannot run, got %d (%v)", count, err)
	}
	if count, _, err := newer.Stranded(ctx); err != nil || count != 0 {
		t.Fatalf("the new replica can run everything, got %d stranded (%v)", count, err)
	}
	if _, err := older.Enqueue(ctx, NewJob{Key: "x", Tenant: "a", Kind: "added", Format: 1, Step: "start"}); !errors.Is(err, ErrUndeclared) {
		t.Fatalf("the old replica admitted a kind it does not declare: %v", err)
	}

	// The lane keeps its order: the successor the old replica could run stays behind the
	// head it could not, and the new replica runs them in order.
	claimed := map[string]bool{}
	for range 4 {
		r := claim(t, ctx, newer)
		if r.job.Key == "lane-next" && !claimed["lane-head"] {
			t.Fatal("the lane's successor ran before its head")
		}
		claimed[r.job.Key] = true
		apply(t, r, Done())
	}
	if len(claimed) != 4 {
		t.Fatalf("the new replica ran %v, want all four", claimed)
	}
}

func TestLanesOfTwoTenantsDoNotShareAHead(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	lane := "inbox"
	enqueue(t, ctx, s, inLane(demo("a-1", "a"), lane, time.Unix(1, 0)))
	first := claim(t, ctx, s)
	// Tenant a's head now retries for an hour and holds a's lane.
	apply(t, first, Retry("transport", time.Hour))

	enqueue(t, ctx, s, inLane(demo("b-1", "b"), lane, time.Unix(1, 0)))
	enqueue(t, ctx, s, inLane(demo("a-2", "a"), lane, time.Unix(2, 0)))
	r := claim(t, ctx, s)
	if r.job.Key != "b-1" {
		t.Fatalf("claimed %s: tenant b's lane must not wait on tenant a's head", r.job.Key)
	}
	// Both lanes have a head at once; a shared head index would reject this.
	due(t, ctx, s, "a-1")
	again := claim(t, ctx, s)
	if again.job.Key != "a-1" {
		t.Fatalf("claimed %s, want tenant a's retrying head", again.job.Key)
	}
	apply(t, r, Done())
	apply(t, again, Done())
	if last := claim(t, ctx, s); last.job.Key != "a-2" {
		t.Fatalf("claimed %s, want a-2 after its head finished", last.job.Key)
	}
}

func TestGatedJobCannotJoinAnOrderedLane(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	// A gated job is resumed by key, which would let a later job overtake its lane.
	if _, err := s.Enqueue(ctx, gated(inLane(demo("job", "tenant"), "lane", time.Unix(1, 0)))); !errors.Is(err, ErrState) {
		t.Fatalf("got %v, want ErrState", err)
	}
	enqueue(t, ctx, s, inLane(demo("ordered", "tenant"), "lane", time.Unix(1, 0)))
	r := claim(t, ctx, s)
	if err := BlockForSecret().apply(ctx, r); !errors.Is(err, ErrState) {
		t.Fatalf("an ordered job became gated at run time: %v", err)
	}
}

func resume(ctx context.Context, s *Store, key string) (*Run, error) {
	r, err := s.claim(ctx, claimRequest{key: key, secret: "live-secret", can: everything(s)})
	if r != nil {
		r.handler = terminalHandler{}
	}
	return r, err
}

func TestGatedJobNeverWorksWithoutItsSecret(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, gated(demo("job", "tenant")))
	first, err := resume(ctx, s, "job")
	if err != nil || first.Secret() != "live-secret" {
		t.Fatalf("resume with a secret: %+v %v", first, err)
	}

	// The worker holding the secret dies: its lease expires with attempts to spare.
	due(t, ctx, s, "job")
	if r, claimErr := tryClaim(ctx, s); !errors.Is(claimErr, errRescheduled) {
		t.Fatalf("the scheduler leased a gated job with no secret: %+v %v", r, claimErr)
	}
	j, err := s.Get(ctx, "job")
	if err != nil || j.State != StateBlocked || j.Attempts != 1 {
		t.Fatalf("the job must wait for its secret again with its attempt spent: %+v %v", j, err)
	}
	if err := first.Save(ctx, "late", []byte("1")); !errors.Is(err, ErrLease) {
		t.Fatalf("the dead holder still wrote: %v", err)
	}
	if r, err := tryClaim(ctx, s); !errors.Is(err, ErrAbsent) {
		t.Fatalf("a blocked job was offered again before its gate timed out: %+v %v", r, err)
	}

	// With its secret it works again; without one, once the budget is spent, a claim only
	// reconciles.
	for attempt := 2; attempt <= s.cfg.MaxAttempts; attempt++ {
		r, err := resume(ctx, s, "job")
		if err != nil || r.job.Attempts != attempt || r.job.intent != nil {
			t.Fatalf("resume %d: %+v %v", attempt, r, err)
		}
		due(t, ctx, s, "job")
		if attempt < s.cfg.MaxAttempts {
			if _, err := tryClaim(ctx, s); !errors.Is(err, errRescheduled) {
				t.Fatalf("takeover %d: %v", attempt, err)
			}
		}
	}
	last := claim(t, ctx, s)
	if last.job.intent == nil || *last.job.intent != CauseLeaseExpired || last.Secret() != "" {
		t.Fatalf("after the last attempt died the claim must only reconcile: %+v", last.job)
	}
}

func TestResumeAfterTheGateTimedOutIsRefused(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, gated(demo("job", "tenant")))
	// The gate's deadline passes before any watcher has looked at the row.
	if _, err := s.pool.Exec(ctx, "UPDATE queue_jobs SET ready_at=clock_timestamp()-interval '1 ms'"); err != nil {
		t.Fatal(err)
	}
	if r, err := resume(ctx, s, "job"); !errors.Is(err, ErrState) {
		t.Fatalf("a resume won after the gate timeout: %+v %v", r, err)
	}
	abandoned := claim(t, ctx, s)
	if abandoned.job.intent == nil || *abandoned.job.intent != testGateAbandoned {
		t.Fatalf("the timed-out gate must be reconciled as abandoned: %+v", abandoned.job)
	}
}

// laterHandler cannot settle the outside state until told to.
type laterHandler struct{ settled *bool }

func (laterHandler) Work(context.Context, *Run) Outcome { return Retry("transport", 0) }

func (h laterHandler) Exhausted(context.Context, *Reconcile) Resolution {
	if *h.settled {
		return Resolved()
	}
	return Later("vendorunavailable", 0)
}

func TestReconciliationIsBoundedAndRepairKeepsTheIntent(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	settled := false
	handler := laterHandler{&settled}
	enqueue(t, ctx, s, withMeta(inLane(demo("stuck", "tenant"), "lane", time.Unix(1, 0)), `"in"`))
	enqueue(t, ctx, s, inLane(demo("behind", "tenant"), "lane", time.Unix(2, 0)))

	step := func() Job {
		t.Helper()
		due(t, ctx, s, "stuck")
		r := claim(t, ctx, s)
		if r.job.Key != "stuck" {
			t.Fatalf("claimed %s while the head still holds the lane", r.job.Key)
		}
		r.handler = handler
		if r.job.intent == nil {
			apply(t, r, r.handler.Work(ctx, r))
		} else if err := r.reconcile(ctx); err != nil {
			t.Fatal(err)
		}
		j, err := s.Get(ctx, "stuck")
		if err != nil {
			t.Fatal(err)
		}
		return j
	}
	var j Job
	// MaxAttempts transient failures exhaust the job; the last one starts reconciling.
	for range s.cfg.MaxAttempts {
		j = step()
	}
	if j.State != StateWaiting || j.ReconcileAttempts != 1 {
		t.Fatalf("after exhaustion the job must be waiting to reconcile again: %+v", j)
	}
	for j.State == StateWaiting {
		j = step()
	}
	if j.State != StateParked || j.Outcome == nil || *j.Outcome != TerminalFailure ||
		j.Reason == nil || *j.Reason != CauseReconcileExhausted || j.ReconcileAttempts != s.cfg.ReconcileMax-1 {
		t.Fatalf("a reconciliation that never settles must park for repair: %+v", j)
	}
	var intent *string
	if err := s.pool.QueryRow(ctx, "SELECT intent FROM queue_jobs WHERE job_key='stuck'").Scan(&intent); err != nil ||
		intent == nil || *intent != "transport" {
		t.Fatalf("the repair state lost the original intent: %v %v", intent, err)
	}
	next := claim(t, ctx, s)
	if next.job.Key != "behind" {
		t.Fatalf("claimed %s: a job parked for repair must release its lane", next.job.Key)
	}
	apply(t, next, Done())

	// An operator fixes the outside world and redrives: the job reconciles, it does not
	// start its work over.
	settled = true
	if err := s.Redrive(ctx, "stuck"); err != nil {
		t.Fatal(err)
	}
	r := claim(t, ctx, s)
	if r.job.intent == nil || r.job.ReconcileAttempts != 0 {
		t.Fatalf("a redriven repair must resume reconciling with a fresh budget: %+v", r.job)
	}
	r.handler = handler
	if err := r.reconcile(ctx); err != nil {
		t.Fatal(err)
	}
	if j, err := s.Get(ctx, "stuck"); err != nil || j.Outcome == nil || *j.Outcome != TerminalSuccess {
		t.Fatalf("the redriven job must finish: %+v %v", j, err)
	}
}

func TestHoldKeepsTheWholeTenantOffTheSchedule(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, demo("held-1", "held"))
	enqueue(t, ctx, s, demo("held-2", "held"))
	r := claim(t, ctx, s)
	apply(t, r, Hold("accountdeleting", time.Hour))
	if j, err := s.Get(ctx, r.job.Key); err != nil || j.Attempts != 0 || j.State != StateWaiting {
		t.Fatalf("a hold must refund the attempt: %+v %v", j, err)
	}
	enqueue(t, ctx, s, demo("free", "other"))
	if next := claim(t, ctx, s); next.job.Key != "free" {
		t.Fatalf("claimed %s, want the other tenant's job", next.job.Key)
	}
	if r, err := tryClaim(ctx, s); !errors.Is(err, ErrAbsent) {
		t.Fatalf("the held tenant's second job was offered: %+v %v", r, err)
	}
}

func TestUndeclaredKindFormatAndStepAreRejected(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	for name, n := range map[string]NewJob{
		"kind":   {Key: "k", Tenant: "tenant", Kind: "nobody", Format: 1, Step: "start"},
		"format": {Key: "k", Tenant: "tenant", Kind: kindDemo, Format: 9, Step: "start"},
		"step":   {Key: "k", Tenant: "tenant", Kind: kindDemo, Format: 1, Step: "nowhere"},
	} {
		if _, err := s.Enqueue(ctx, n); !errors.Is(err, ErrUndeclared) {
			t.Errorf("undeclared %s: got %v, want ErrUndeclared", name, err)
		}
	}
	enqueue(t, ctx, s, demo("job", "tenant"))
	r := claim(t, ctx, s)
	if err := r.Save(ctx, "nowhere", []byte("1")); !errors.Is(err, ErrUndeclared) {
		t.Errorf("save to an undeclared step: %v", err)
	}
	if err := r.SetStep(ctx, "nowhere"); !errors.Is(err, ErrUndeclared) {
		t.Errorf("move to an undeclared step: %v", err)
	}
}

func TestOpenRejectsInvalidPolicyAndDeclarations(t *testing.T) {
	t.Parallel()
	valid := testConfig()
	if err := valid.Validate(); err != nil {
		t.Fatalf("the test policy must be valid: %v", err)
	}
	for name, change := range map[string]func(*Config){
		"no lease":            func(c *Config) { c.Lease = 0 },
		"no backoff":          func(c *Config) { c.Backoff = 0 },
		"no attempts":         func(c *Config) { c.MaxAttempts = 0 },
		"no deterministic":    func(c *Config) { c.DeterministicMax = 0 },
		"no reconcile budget": func(c *Config) { c.ReconcileMax = 0 },
		"no workers":          func(c *Config) { c.Workers = 0 },
		"no gate timeout":     func(c *Config) { c.GateTimeout = 0 },
		"no gate cause":       func(c *Config) { c.GateAbandoned = "" },
		"negative delay":      func(c *Config) { c.BudgetDelay = -1 },
	} {
		cfg := valid
		change(&cfg)
		// The URL is never dialled: validation comes first.
		if _, err := Open(t.Context(), "postgres://invalid.invalid/x", cfg, testKinds(), nil, nil); !errors.Is(err, ErrConfig) {
			t.Errorf("%s: got %v, want ErrConfig", name, err)
		}
	}
	for name, kinds := range map[string][]Kind{
		"no name":        {{Formats: []int{1}, Steps: []string{"s"}}},
		"no formats":     {{Name: "k", Steps: []string{"s"}}},
		"format zero":    {{Name: "k", Formats: []int{0}, Steps: []string{"s"}}},
		"no steps":       {{Name: "k", Formats: []int{1}}},
		"declared twice": {{Name: "k", Formats: []int{1}, Steps: []string{"s"}}, {Name: "k", Formats: []int{1}, Steps: []string{"s"}}},
		"reserved name":  {{Name: "unknown", Formats: []int{1}, Steps: []string{"s"}}},
	} {
		if _, err := newRegistry(valid, kinds); !errors.Is(err, ErrConfig) {
			t.Errorf("%s: got %v, want ErrConfig", name, err)
		}
	}
}

func TestMigrateRefusesAnEditedMigration(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	if err := s.Ready(ctx); err != nil {
		t.Fatalf("a freshly migrated database must be ready: %v", err)
	}
	if err := s.Migrate(ctx); err != nil {
		t.Fatalf("migrating twice must be a no-op: %v", err)
	}
	if _, err := s.pool.Exec(ctx, "UPDATE queue_schema SET checksum='edited-after-apply'"); err != nil {
		t.Fatal(err)
	}
	if err := s.Migrate(ctx); !errors.Is(err, ErrSchema) {
		t.Errorf("Migrate accepted a file that differs from what was applied: %v", err)
	}
	if err := s.Ready(ctx); !errors.Is(err, ErrSchema) {
		t.Errorf("Ready accepted a file that differs from what was applied: %v", err)
	}
}

func TestUndeclaredCauseIsRecordedAsUnknown(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, demo("job", "tenant"))
	apply(t, claim(t, ctx, s), Retry("nobody-declared-this", time.Hour))
	if j, err := s.Get(ctx, "job"); err != nil || j.Reason == nil || *j.Reason != CauseUnknown {
		t.Fatalf("got %+v %v, want reason unknown", j, err)
	}
}
