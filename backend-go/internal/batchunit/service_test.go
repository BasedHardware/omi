package batchunit_test

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

// These tests run the handler on real workers against Postgres (queuetest). The vendor and
// the result store are in-memory stand-ins that keep the ledger a real one keeps: what was
// charged, per operation, and what was stored.

const (
	causeVendorDown queue.Cause = "vendor_down"
	causeStoreDown  queue.Cause = "store_down"
	causeDeleting   queue.Cause = "owner_deleting"
	spoken                      = "the words that were spoken"
)

// classified is an adapter error that tells the queue what to do.
type classified struct{ outcome queue.Outcome }

func (classified) Error() string            { return "classified adapter failure" }
func (c classified) Outcome() queue.Outcome { return c.outcome }

func transient(c queue.Cause) error { return classified{queue.Retry(c, 0)} }

// vendor charges once per operation and remembers every result it committed.
type vendor struct {
	mu         sync.Mutex
	committed  map[string]string
	charges    int
	operations []string
	// failBefore fails that many calls before anything is charged.
	failBefore int
	// loseResponses fails that many calls after the charge is committed.
	loseResponses int
}

func (v *vendor) Transcribe(_ context.Context, g queue.Guarded, req batchunit.Request) (batchunit.Transcript, error) {
	if err := g.Err(); err != nil {
		return batchunit.Transcript{}, err
	}
	v.mu.Lock()
	defer v.mu.Unlock()
	v.operations = append(v.operations, req.Operation)
	if v.failBefore > 0 {
		v.failBefore--
		return batchunit.Transcript{}, transient(causeVendorDown)
	}
	if _, done := v.committed[req.Operation]; !done {
		v.charges++
		v.committed[req.Operation] = spoken + " in " + req.Source.Ref
	}
	if v.loseResponses > 0 {
		v.loseResponses--
		return batchunit.Transcript{}, transient(causeVendorDown)
	}
	return batchunit.Transcript{Text: v.committed[req.Operation]}, nil
}

func (v *vendor) Recover(_ context.Context, g queue.Guarded, req batchunit.Request) (batchunit.Transcript, error) {
	if err := g.Err(); err != nil {
		return batchunit.Transcript{}, err
	}
	v.mu.Lock()
	defer v.mu.Unlock()
	text, done := v.committed[req.Operation]
	if !done {
		return batchunit.Transcript{}, batchunit.ErrNotCommitted
	}
	return batchunit.Transcript{Text: text}, nil
}

// results keeps one transcription per operation.
type results struct {
	mu     sync.Mutex
	stored map[string]string
	// down fails that many writes.
	down int
}

func (s *results) Put(_ context.Context, g queue.Guarded, req batchunit.Request, t batchunit.Transcript) (batchunit.Receipt, error) {
	if err := g.Err(); err != nil {
		return batchunit.Receipt{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.down > 0 {
		s.down--
		return batchunit.Receipt{}, transient(causeStoreDown)
	}
	s.stored[req.Operation] = t.Text
	return batchunit.Receipt{Operation: req.Operation, Result: "results/" + req.Owner + "/" + req.UnitID}, nil
}

type accounts struct {
	mu       sync.Mutex
	deleting map[string]bool
}

func (a *accounts) is(owner string) bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.deleting[owner]
}

func (a *accounts) Admissible(_ context.Context, admitting queue.Admitting, owner string) (queue.EntitlementSnapshot, error) {
	if err := admitting.Err(); err != nil {
		return queue.EntitlementSnapshot{}, err
	}
	if a.is(owner) {
		return queue.EntitlementSnapshot{}, classified{queue.Hold(causeDeleting, time.Hour)}
	}
	return queue.EntitlementSnapshot{}, nil
}

func (a *accounts) Runnable(_ context.Context, g queue.Guarded, owner string) error {
	if err := g.Err(); err != nil {
		return err
	}
	if a.is(owner) {
		return classified{queue.Hold(causeDeleting, time.Hour)}
	}
	return nil
}

type counts struct {
	mu                  sync.Mutex
	admitted, replayed  int
	transcribed, reused int
}

func (c *counts) Admitted(replay bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if replay {
		c.replayed++
	} else {
		c.admitted++
	}
}

func (c *counts) Transcribed(reused bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if reused {
		c.reused++
	} else {
		c.transcribed++
	}
}

type rig struct {
	*queuetest.Harness
	service  *batchunit.Service
	vendor   *vendor
	results  *results
	accounts *accounts
}

func newRig(t *testing.T) *rig {
	t.Helper()
	h := queuetest.Open(t, queuetest.Policy(), batchunit.Declaration(causeVendorDown, causeStoreDown, causeDeleting))
	r := &rig{
		Harness: h, vendor: &vendor{committed: map[string]string{}}, results: &results{stored: map[string]string{}},
		accounts: &accounts{deleting: map[string]bool{}},
	}
	r.service = &batchunit.Service{
		Queue: h.Store, Speech: r.vendor, Results: r.results, Accounts: r.accounts, Observer: &counts{},
		Keys: func(owner, unitID string) string { return owner + "/" + unitID },
	}
	return r
}

func (r *rig) start() { r.Start(map[string]queue.Handler{batchunit.Kind: r.service}) }

func (r *rig) admit(t *testing.T, u batchunit.Unit) queue.Job {
	t.Helper()
	job, err := r.service.Admit(t.Context(), "owner", u)
	if err != nil {
		t.Fatal(err)
	}
	return job
}

func (v *vendor) ledger() (charges int, operations []string) {
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.charges, append([]string(nil), v.operations...)
}

func TestUnitIsTranscribedStoredAndChargedOnce(t *testing.T) {
	t.Parallel()
	r := newRig(t)
	r.start()
	job := r.admit(t, unit("u1", "audio/u1"))
	done := r.Settled(job.Key)
	if *done.Outcome != queue.TerminalSuccess || done.Attempts != 1 || done.Step != batchunit.StepStored {
		t.Fatalf("got %+v", done)
	}
	receipt, ok := batchunit.Stored(done.Checkpoint)
	if !ok || receipt.Result != "results/owner/u1" {
		t.Fatalf("the finished job must hold its receipt: %s", done.Checkpoint)
	}
	if charges, _ := r.vendor.ledger(); charges != 1 {
		t.Errorf("charged %d times, want 1", charges)
	}
	if r.results.stored[receipt.Operation] == "" {
		t.Error("the receipt points at nothing")
	}
	// The row keeps where things are, never what they say.
	var row string
	conn, err := pgx.Connect(t.Context(), r.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if closeErr := conn.Close(context.WithoutCancel(t.Context())); closeErr != nil {
			t.Error(closeErr)
		}
	}()
	err = conn.QueryRow(t.Context(), "SELECT row_to_json(j)::text FROM queue_jobs j WHERE job_key=$1", job.Key).Scan(&row)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(row, spoken) {
		t.Errorf("the job row holds transcript text: %s", row)
	}
	if reports := r.Reports(); len(reports) != 0 {
		t.Errorf("unexpected reports: %v", reports)
	}
}

func TestALostVendorResponseIsRetriedWithTheSameOperationAndChargedOnce(t *testing.T) {
	t.Parallel()
	r := newRig(t)
	r.vendor.loseResponses = 1
	r.start()
	done := r.Settled(r.admit(t, unit("u1", "audio/u1")).Key)
	charges, operations := r.vendor.ledger()
	if *done.Outcome != queue.TerminalSuccess || done.Attempts != 2 || charges != 1 {
		t.Fatalf("got %+v with %d charge(s): the retry must reuse the committed result", done, charges)
	}
	if len(operations) != 2 || operations[0] != operations[1] {
		t.Fatalf("the retry sent a different operation: %v", operations)
	}
}

func TestAPaidResultIsRecoveredWhenTheLastAttemptCouldNotRecordIt(t *testing.T) {
	t.Parallel()
	r := newRig(t)
	// Every attempt pays (once) and then fails to store, so no receipt is ever saved and
	// the attempt budget runs out with a committed result at the vendor.
	r.results.down = queuetest.Policy().MaxAttempts
	r.start()
	done := r.Settled(r.admit(t, unit("u1", "audio/u1")).Key)
	charges, _ := r.vendor.ledger()
	if *done.Outcome != queue.TerminalSuccess || charges != 1 {
		t.Fatalf("got %+v with %d charge(s): a paid result must be recovered, not parked", done, charges)
	}
	if done.Attempts != queuetest.Policy().MaxAttempts {
		t.Errorf("recovery must not spend extra attempts: %d", done.Attempts)
	}
	if receipt, ok := batchunit.Stored(done.Checkpoint); !ok || r.results.stored[receipt.Operation] == "" {
		t.Errorf("the recovered result was not stored: %s", done.Checkpoint)
	}
}

func TestAUnitTheVendorNeverCommittedParksWithItsCause(t *testing.T) {
	t.Parallel()
	r := newRig(t)
	r.vendor.failBefore = 1 << 20
	r.start()
	done := r.Settled(r.admit(t, unit("u1", "audio/u1")).Key)
	charges, _ := r.vendor.ledger()
	if done.State != queue.StateParked || *done.Outcome != queue.TerminalFailure ||
		done.Reason == nil || *done.Reason != causeVendorDown || charges != 0 {
		t.Fatalf("got %+v with %d charge(s)", done, charges)
	}
}

func TestAnOwnerBeingDeletedIsHeldBeforeAnythingIsPaid(t *testing.T) {
	t.Parallel()
	r := newRig(t)
	first := r.admit(t, unit("u1", "audio/u1"))
	second := r.admit(t, unit("u2", "audio/u2"))
	r.accounts.mu.Lock()
	r.accounts.deleting["owner"] = true
	r.accounts.mu.Unlock()
	r.start()
	held := r.Until(first.Key, "it is held", func(j queue.Job) bool { return j.State == queue.StateWaiting })
	if held.Attempts != 0 || held.Reason == nil || *held.Reason != causeDeleting {
		t.Fatalf("a held unit must keep its attempts: %+v", held)
	}
	if charges, _ := r.vendor.ledger(); charges != 0 {
		t.Errorf("paid %d time(s) for an owner being deleted", charges)
	}
	if next, err := r.Store.Get(t.Context(), second.Key); err != nil || next.Attempts != 0 || next.State != queue.StateReady {
		t.Errorf("the owner's next unit must not be tried while the owner is held: %+v %v", next, err)
	}
	if _, err := r.service.Admit(t.Context(), "owner", unit("u3", "audio/u3")); err == nil {
		t.Error("admitted a new unit for an owner being deleted")
	}
}

func TestAdmittingAUnitTwiceReturnsTheFirstJob(t *testing.T) {
	t.Parallel()
	r := newRig(t)
	first := r.admit(t, unit("u1", "audio/first"))
	second := r.admit(t, unit("u1", "audio/later"))
	source, err := batchunit.Input(second.Meta)
	if first.Key != second.Key || err != nil || source.Ref != "audio/first" {
		t.Fatalf("the first admission must fix the input: %+v %v", source, err)
	}
}

func TestAnOwnersUnitsRunInOrderOneAtATime(t *testing.T) {
	t.Parallel()
	r := newRig(t)
	at := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	var keys []string
	for i, id := range []string{"c", "a", "b"} {
		u := unit(id, "audio/"+id)
		u.OrderAt = at.Add(-time.Duration(i) * time.Minute)
		keys = append(keys, r.admit(t, u).Key)
	}
	r.start()
	for _, key := range keys {
		r.Settled(key)
	}
	_, operations := r.vendor.ledger()
	// Order time decides: b (earliest), then a, then c.
	want := []string{"owner/b", "owner/a", "owner/c"}
	if len(operations) != len(want) {
		t.Fatalf("got %d calls, want %d", len(operations), len(want))
	}
	for i, key := range want {
		if operations[i] != queue.GuardedForTest(t, "owner", key).Operation(batchunit.StepSpeech) {
			t.Errorf("call %d was not for %s", i, key)
		}
	}
}

func TestACorruptedStoredInputParksInsteadOfLooping(t *testing.T) {
	t.Parallel()
	r := newRig(t)
	job := r.admit(t, unit("u1", "audio/u1"))
	conn, err := pgx.Connect(t.Context(), r.URL)
	if err != nil {
		t.Fatal(err)
	}
	_, err = conn.Exec(t.Context(), `UPDATE queue_jobs SET meta='{"version":1}' WHERE job_key=$1`, job.Key)
	if closeErr := conn.Close(context.WithoutCancel(t.Context())); err != nil || closeErr != nil {
		t.Fatal(errors.Join(err, closeErr))
	}
	r.start()
	done := r.Settled(job.Key)
	if done.State != queue.StateParked || done.Reason == nil || *done.Reason != batchunit.CauseInputUnreadable {
		t.Fatalf("got %+v", done)
	}
	if charges, _ := r.vendor.ledger(); charges != 0 {
		t.Errorf("paid %d time(s) for an unreadable input", charges)
	}
}

// Recovery uses the original operation and bypasses a funding hold without
// starting another transcription, including if the paid vendor has lost its receipt.
func TestPaidResultRecoveryWhileHeldNeverTranscribes(t *testing.T) {
	t.Parallel()
	r := newRig(t)
	if err := r.Store.HoldCondition(t.Context(), "owner", queue.Entitlement, 1); err != nil {
		t.Fatal(err)
	}
	u := unit("recover", "audio/recover")
	u.AlreadyPaid = true
	j := r.admit(t, u)
	r.start()
	done := r.Settled(j.Key)
	charges, calls := r.vendor.ledger()
	if done.Attempts == 0 || done.Outcome == nil || *done.Outcome != queue.TerminalFailure || charges != 0 || len(calls) != 0 {
		t.Fatalf("missing paid result: job=%+v charges=%d transcriptions=%d", done, charges, len(calls))
	}
}
