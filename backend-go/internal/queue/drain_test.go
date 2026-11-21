package queue

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

func TestDrainLetsRunningHandlerSaveAndFinish(t *testing.T) {
	t.Parallel()
	ctx, s := workerStore(t)
	entered, finish := make(chan struct{}), make(chan struct{})
	w, reports := run(t, ctx, s, funcHandler{work: func(work context.Context, r *Run) Outcome {
		close(entered)
		select {
		case <-work.Done():
			return Abort()
		case <-finish:
		}
		if err := r.Save(work, "late", []byte("42")); err != nil {
			t.Error(err)
			return Abort()
		}
		return Done()
	}})
	enqueue(t, ctx, s, demo("running", "owner"))
	select {
	case <-entered:
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	}
	drained := make(chan error, 1)
	go func() { drained <- w.Drain(ctx) }()
	<-w.done
	enqueue(t, ctx, s, demo("next", "owner"))
	if err := w.Resume(ctx, "next", "secret"); !errors.Is(err, ErrStopped) {
		t.Fatalf("resume during drain: %v", err)
	}
	// Observe a renewal during the grace period using the database clock.
	var initial time.Time
	if err := s.pool.QueryRow(ctx, "SELECT lease_until FROM queue_jobs WHERE job_key='running'").Scan(&initial); err != nil {
		t.Fatal(err)
	}
	eventually(t, ctx, "the draining worker renews its lease", func() bool {
		var renewed bool
		if err := s.pool.QueryRow(ctx, "SELECT lease_until>$1 FROM queue_jobs WHERE job_key='running'", initial).Scan(&renewed); err != nil {
			t.Fatal(err)
		}
		return renewed
	})
	close(finish)
	if err := <-drained; err != nil {
		t.Fatal(err)
	}
	if j, err := s.Get(ctx, "running"); err != nil || j.State != StateCompleted || string(j.Checkpoint) != "42" || j.Attempts != 1 {
		t.Fatalf("drained handler: %+v %v", j, err)
	}
	if j, err := s.Get(ctx, "next"); err != nil || j.State != StateReady || j.Attempts != 0 || len(reports.all()) != 0 {
		t.Fatalf("queued during drain: %+v %v; reports %v", j, err, reports.all())
	}
}

func TestDrainDeadlineRefundsWorkAndReconciliationForAnotherReplica(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t) // one-minute lease
	s.cfg.DeterministicMax = 1
	entered := make(chan Job, 3)
	unblock := make(chan struct{})
	var unblockOnce sync.Once
	releaseHandlers := func() { unblockOnce.Do(func() { close(unblock) }) }
	wait := func(work context.Context, j Job) {
		entered <- j
		<-work.Done()
		<-unblock // simulate an adapter slow to return from cancellation
	}
	w, reports := run(t, ctx, s, funcHandler{
		work: func(work context.Context, r *Run) Outcome {
			if err := r.Save(work, "late", []byte("42")); err != nil {
				t.Error(err)
				return Abort()
			}
			if r.Job().Key == "reconcile" {
				return Fail("vendorrejected")
			}
			wait(work, r.Job())
			return Done()
		},
		exhausted: func(work context.Context, r *Reconcile) Resolution {
			wait(work, r.Job())
			return Resolved()
		},
	})
	t.Cleanup(releaseHandlers)
	enqueue(t, ctx, s, demo("normal", "owner"))
	for _, key := range []string{"secret", "reconcile"} {
		enqueue(t, ctx, s, gated(demo(key, "owner")))
		if err := w.Resume(ctx, key, "present"); err != nil {
			t.Fatal(err)
		}
	}
	claims := make(map[string]Job)
	for range 3 {
		select {
		case j := <-entered:
			claims[j.Key] = j
		case <-ctx.Done():
			t.Fatal(ctx.Err())
		}
	}
	grace, cancel := context.WithTimeout(ctx, 20*time.Millisecond)
	defer cancel()
	drained := make(chan error, 1)
	go func() { drained <- w.Drain(grace) }()
	select {
	case err := <-drained:
		if !errors.Is(err, context.DeadlineExceeded) {
			t.Fatalf("drain: %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("drain waited for handlers that ignored cancellation")
	}
	// Drain refunds the claims at the deadline but deliberately doesn't wait for handlers
	// that ignore cancellation. Release and join them before asserting what they reported.
	releaseHandlers()
	w.Stop()
	for key := range claims {
		j, err := s.Get(ctx, key)
		want := StateReady
		if key == "secret" {
			want = StateBlocked
		}
		if err != nil || j.State != want || j.Attempts != 0 || j.Step != "late" || string(j.Checkpoint) != "42" {
			t.Fatalf("returned %s: %+v %v", key, j, err)
		}
	}
	peer, peerReports := run(t, ctx, s, funcHandler{
		work: func(_ context.Context, r *Run) Outcome {
			if r.Job().Key == "reconcile" || (r.Job().Key == "secret" && r.Secret() != "fresh") {
				t.Errorf("wrong work handoff for %s", r.Job().Key)
			}
			return Done()
		},
		exhausted: func(_ context.Context, r *Reconcile) Resolution {
			if r.Job().Key != "reconcile" || r.Cause() != "vendorrejected" || r.Job().ReconcileAttempts != 0 {
				t.Errorf("wrong reconciliation handoff: %+v", r.Job())
			}
			return Resolved()
		},
	})
	if err := peer.Resume(ctx, "secret", "fresh"); err != nil {
		t.Fatal(err)
	}
	for key, previous := range claims {
		eventually(t, ctx, "peer completes "+key, finished(t, ctx, s, key))
		j, err := s.Get(ctx, key)
		if err != nil || j.Token <= previous.Token || j.Attempts != previous.Attempts || j.Outcome == nil || *j.Outcome != TerminalSuccess {
			t.Fatalf("peer claim for %s: %+v %v", key, j, err)
		}
	}
	peer.Stop()
	if len(reports.all())+len(peerReports.all()) != 0 {
		t.Fatalf("worker reports: %v, %v", reports.all(), peerReports.all())
	}
}
