package batchdocs_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/batchdocs"
	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

const spoken = "the words that were spoken"

func adapter(b docstoretest.Bench) (batchdocs.Results, crypt.Codec) {
	codec := crypt.New("a test-only encryption secret")
	at := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	return batchdocs.Results{Docs: b.Store, Codec: codec, Clock: clock.Fixed{T: at}}, codec
}

func request(operation string) batchunit.Request {
	return batchunit.Request{Operation: operation, Owner: "owner", UnitID: "u1", Source: batchunit.Source{Ref: "audio/u1"}}
}

func outcomeOf(t *testing.T, err error) queue.Outcome {
	t.Helper()
	classified, ok := errors.AsType[queue.Classified](err)
	if !ok {
		t.Fatalf("the adapter returned an unclassified error: %v", err)
	}
	return classified.Outcome()
}

func TestPutStoresTheTranscriptEncryptedAndReturnsItsLocation(t *testing.T) {
	t.Parallel()
	b := docstoretest.Open(t)
	results, codec := adapter(b)
	g := queue.GuardedForTest(t, "owner", "job")
	receipt, err := results.Put(t.Context(), g, request("op_1"), batchunit.Transcript{Text: spoken})
	if err != nil {
		t.Fatal(err)
	}
	if receipt.Operation != "op_1" || receipt.Result != "users/owner/batch_unit_results/u1" {
		t.Fatalf("receipt: %+v", receipt)
	}
	snapshot, err := b.Raw.Doc(receipt.Result).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	stored, isText := snapshot.Data()["transcript"].(string)
	if !isText || stored == "" || strings.Contains(stored, spoken) {
		t.Fatalf("the transcript must be stored encrypted, got %q", stored)
	}
	plain, err := codec.Open("owner", stored)
	if err != nil || string(plain) != spoken {
		t.Fatalf("the stored transcript does not decrypt with the owner's key: %q %v", plain, err)
	}
	if _, err := codec.Open("someone-else", stored); err == nil {
		t.Error("another owner's key decrypted the transcript")
	}
}

func TestPutIsIdempotentPerOperationAndRefusesADifferentOne(t *testing.T) {
	t.Parallel()
	b := docstoretest.Open(t)
	results, _ := adapter(b)
	g := queue.GuardedForTest(t, "owner", "job")
	first, err := results.Put(t.Context(), g, request("op_1"), batchunit.Transcript{Text: spoken})
	if err != nil {
		t.Fatal(err)
	}
	before, err := b.Raw.Doc(first.Result).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	again, err := results.Put(t.Context(), g, request("op_1"), batchunit.Transcript{Text: "a different reading"})
	if err != nil || again != first {
		t.Fatalf("a repeat must return the first receipt: %+v %v", again, err)
	}
	after, err := b.Raw.Doc(first.Result).Get(t.Context())
	if err != nil || !after.UpdateTime.Equal(before.UpdateTime) {
		t.Fatalf("a repeat rewrote the document: %v", err)
	}
	_, err = results.Put(t.Context(), g, request("op_2"), batchunit.Transcript{Text: spoken})
	if err == nil {
		t.Fatal("a different operation overwrote the unit's result")
	}
	if got := outcomeOf(t, err); got != queue.Fail(batchdocs.CauseResultConflict) {
		t.Errorf("a conflicting operation must fail deterministically, got %#v", got)
	}
}

func TestPutHoldsAnOwnerBeingDeletedAndWritesNothing(t *testing.T) {
	t.Parallel()
	b := docstoretest.Open(t)
	results, _ := adapter(b)
	b.Mark(t, "owner", map[string]any{"wipe_status": "pending_deletion"})
	_, err := results.Put(t.Context(), queue.GuardedForTest(t, "owner", "job"), request("op_1"),
		batchunit.Transcript{Text: spoken})
	if !errors.Is(err, docstore.ErrOwnerDeleting) {
		t.Fatalf("got %v, want ErrOwnerDeleting", err)
	}
	if got := outcomeOf(t, err); got != queue.Hold(batchdocs.CauseOwnerDeleting, time.Minute) {
		t.Errorf("an owner being deleted must hold the tenant, got %#v", got)
	}
	if b.Exists(t, "users/owner/batch_unit_results/u1") {
		t.Error("a result was written for an owner being deleted")
	}
}

func TestPutWithAnEndedGuardWritesNothingAndAborts(t *testing.T) {
	t.Parallel()
	b := docstoretest.Open(t)
	results, _ := adapter(b)
	_, err := results.Put(t.Context(), queue.Guarded{}, request("op_1"), batchunit.Transcript{Text: spoken})
	if !errors.Is(err, queue.ErrLease) || b.Exists(t, "users/owner/batch_unit_results/u1") {
		t.Fatalf("got %v", err)
	}
}

// vendor is a paid vendor that always succeeds.
type vendor struct{}

func (vendor) Transcribe(context.Context, queue.Guarded, batchunit.Request) (batchunit.Transcript, error) {
	return batchunit.Transcript{Text: spoken}, nil
}

func (vendor) Recover(context.Context, queue.Guarded, batchunit.Request) (batchunit.Transcript, error) {
	return batchunit.Transcript{}, batchunit.ErrNotCommitted
}

type anyone struct{}

func (anyone) Admissible(context.Context, queue.Admitting, string) error { return nil }
func (anyone) Runnable(context.Context, queue.Guarded, string) error     { return nil }

type quiet struct{}

func (quiet) Admitted(bool)    {}
func (quiet) Transcribed(bool) {}

// lateWriter is the failure the receiver-side fence exists for. Just before the write, the
// worker's database session dies (taking the queue's guard locks with it) and the tenant is
// erased, with the deletion marker set the way the real deletion starts. The write is then
// attempted anyway, as it would be by a worker that has not noticed yet.
type lateWriter struct {
	t          *testing.T
	inner      batchdocs.Results
	bench      docstoretest.Bench
	harness    *queuetest.Harness
	siblingPID int32
	result     chan error
}

func (w lateWriter) Put(
	ctx context.Context, g queue.Guarded, req batchunit.Request, tr batchunit.Transcript,
) (batchunit.Receipt, error) {
	admin, err := pgx.Connect(ctx, w.harness.URL)
	if err != nil {
		w.result <- err
		return batchunit.Receipt{}, err
	}
	// pgtest gives this harness a unique database. Only the session pinned
	// inside Guard owns the job's exclusive advisory lock; an idle pooled
	// connection can still show its last query in pg_stat_activity.
	var ownCandidates int
	var siblingCandidate bool
	err = admin.QueryRow(ctx, `SELECT
 (SELECT count(*) FROM pg_stat_activity a
  WHERE a.datname=current_database() AND a.query LIKE 'SELECT queue_acquire_guard(%'
  AND EXISTS (SELECT 1 FROM pg_locks l WHERE l.pid=a.pid AND l.locktype='advisory'
              AND l.mode='ExclusiveLock' AND l.granted)),
 EXISTS (SELECT 1 FROM pg_stat_activity a
  WHERE a.pid=$1 AND a.datname<>current_database() AND a.query LIKE 'SELECT queue_acquire_guard(%'
  AND EXISTS (SELECT 1 FROM pg_locks l WHERE l.pid=a.pid AND l.locktype='advisory'
              AND l.mode='ExclusiveLock' AND l.granted))`, w.siblingPID).Scan(&ownCandidates, &siblingCandidate)
	if err == nil && (ownCandidates != 1 || !siblingCandidate) {
		err = errors.New("the test must have one local guard candidate and a matching sibling candidate")
	}
	if err != nil {
		closeErr := admin.Close(ctx)
		w.result <- errors.Join(err, closeErr)
		return batchunit.Receipt{}, errors.New("test setup failed")
	}
	var killed bool
	err = admin.QueryRow(ctx, `SELECT coalesce((
 SELECT pg_terminate_backend(pid => a.pid, timeout => 5000)
 FROM pg_stat_activity a
 WHERE a.datname=current_database() AND a.query LIKE 'SELECT queue_acquire_guard(%'
 AND EXISTS (SELECT 1 FROM pg_locks l WHERE l.pid=a.pid AND l.locktype='advisory'
             AND l.mode='ExclusiveLock' AND l.granted)
), false)`).Scan(&killed)
	closeErr := admin.Close(ctx)
	if err != nil || closeErr != nil || !killed {
		w.result <- errors.Join(err, closeErr, errors.New("could not end the guard session in the test database"))
		return batchunit.Receipt{}, errors.New("test setup failed")
	}
	// With the guard's session gone, nothing in Postgres stops the erase any more.
	eraseCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
	defer cancel()
	err = w.harness.Store.Erase(eraseCtx, req.Owner, func() error {
		w.bench.Mark(w.t, req.Owner, map[string]any{"wipe_status": "pending"})
		return nil
	})
	if err != nil {
		w.result <- errors.Join(errors.New("the erase did not complete"), err)
		return batchunit.Receipt{}, err
	}
	// The worker "has not noticed": its context is still live when it writes. Detach from the
	// attempt's cancellation so the test proves the store refuses, not that a timeout fired.
	late, stop := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
	defer stop()
	receipt, err := w.inner.Put(late, g, req, tr)
	w.result <- err
	return receipt, err
}

type siblingGuardSession struct {
	conn *pgx.Conn
	pid  int32
}

// siblingGuard leaves an indistinguishable guard query and advisory locks in
// a different test database on the same server, as a parallel test can.
func siblingGuard(t *testing.T) siblingGuardSession {
	t.Helper()
	h := queuetest.Open(t, queuetest.Policy(), batchunit.Declaration(batchdocs.Causes()...))
	conn, err := pgx.Connect(t.Context(), h.URL)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.WithoutCancel(t.Context()), 5*time.Second)
		defer cancel()
		if err := conn.Close(ctx); err != nil {
			t.Error(err)
		}
	})
	var pid int32
	if err := conn.QueryRow(t.Context(), "SELECT pg_backend_pid()").Scan(&pid); err != nil {
		t.Fatal(err)
	}
	// The function takes session locks before checking the lease. Keep the
	// connection pinned with those locks through the other harness's erase.
	// This must be its final query so pg_stat_activity keeps the same query text
	// as the guard session in the main test database.
	if _, err := conn.Exec(t.Context(), "SELECT queue_acquire_guard($1,$2,$3)", "owner", "owner/sibling-u1", int64(1)); err != nil {
		t.Fatal(err)
	}
	return siblingGuardSession{conn: conn, pid: pid}
}

func TestAWriteThatOutlivesItsGuardIsRefusedByFirestoreAfterAnErase(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	results, _ := adapter(bench)
	h := queuetest.Open(t, queuetest.Policy(), batchunit.Declaration(batchdocs.Causes()...))
	sibling := siblingGuard(t)
	late := lateWriter{
		t: t, inner: results, bench: bench, harness: h, siblingPID: sibling.pid, result: make(chan error, 1),
	}
	service := &batchunit.Service{
		Queue: h.Store, Speech: vendor{}, Results: late, Accounts: anyone{}, Observer: quiet{},
		Keys: func(owner, unitID string) string { return owner + "/" + unitID },
	}
	unit := batchunit.Unit{ID: "u1", Source: batchunit.Source{Ref: "audio/u1"}, OrderAt: time.Unix(1, 0)}
	job, err := service.Admit(t.Context(), "owner", unit)
	if err != nil {
		t.Fatal(err)
	}
	h.Start(map[string]queue.Handler{batchunit.Kind: service})

	select {
	case err := <-late.result:
		if !errors.Is(err, docstore.ErrOwnerDeleting) {
			t.Fatalf("the late write was not refused by the deletion fence: %v", err)
		}
	case <-time.After(90 * time.Second):
		t.Fatal("the handler never reached the write")
	}
	if err := sibling.conn.Ping(t.Context()); err != nil {
		t.Fatalf("the sibling guard session was interrupted: %v", err)
	}
	if bench.Exists(t, "users/owner/batch_unit_results/u1") {
		t.Fatal("a result was written for an erased owner")
	}
	if _, err := h.Store.Get(t.Context(), job.Key); !errors.Is(err, queue.ErrAbsent) {
		t.Fatalf("the erased owner's job is still there: %v", err)
	}
	if _, err := service.Admit(t.Context(), "owner", unit); !errors.Is(err, queue.ErrErased) {
		t.Fatalf("an erased owner was admitted again: %v", err)
	}
}
