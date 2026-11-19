package integrations

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

type finalizer struct {
	service integrationfanout.Service
	targets []integrationfanout.Target
}

func (f finalizer) Work(ctx context.Context, run *queue.Run) queue.Outcome {
	rev, err := strconv.ParseInt(run.Job().Key, 10, 64)
	if err != nil {
		return queue.Fail(integrationfanout.CauseInvalid)
	}
	event := integrationfanout.Event{
		ConversationID: run.Job().Subject, Revision: rev, FanoutKey: "fanout-revision-" + run.Job().Key,
		Locked: run.Job().Subject == "locked", Discarded: run.Job().Subject == "discarded",
	}
	dropped, err := f.service.Deliver(ctx, run, event, f.targets)
	switch {
	case err != nil:
		return queue.FromError(err, integrationfanout.CauseRetry)
	case dropped:
		return queue.DoneWith(integrationfanout.CauseDropped)
	default:
		return queue.Done()
	}
}

func (finalizer) Exhausted(context.Context, *queue.Reconcile) queue.Resolution { return queue.Park() }

func startFanout(t *testing.T, bench docstoretest.Bench, receiver *httptest.Server, targets ...integrationfanout.Target) *queuetest.Harness {
	t.Helper()
	h := queuetest.Open(t, queuetest.Policy(), queue.Kind{
		Name: "test_finalization", Formats: []int{1}, Steps: []string{"integrations"}, Causes: integrationfanout.Causes(),
	})
	s := testSender(t, receiver, 2*time.Second)
	h.Start(map[string]queue.Handler{"test_finalization": finalizer{
		service: integrationfanout.Service{Sender: s, Receipts: Receipts{Store: bench.Store}}, targets: targets,
	}})
	return h
}

func enqueue(t *testing.T, h *queuetest.Harness, key, subject string) {
	t.Helper()
	if _, err := h.Store.Enqueue(t.Context(), queue.NewJob{
		Key: key, Subject: subject, Tenant: "owner", Kind: "test_finalization", Format: 1, Step: "integrations",
	}); err != nil {
		t.Fatal(err)
	}
}

func target(app, url string) integrationfanout.Target {
	return integrationfanout.Target{AppID: app, Enabled: true, Created: true, URL: url, Body: []byte(`{"id":"conversation"}`)}
}

func TestFanoutRetriesOnlyUnsettledReceiversAndIsRevisionScoped(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	var accepted, rejected, developer, disabled, ambiguous atomic.Int32
	var mu sync.Mutex
	effects := make(map[string]bool)
	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/ambiguous":
			ambiguous.Add(1)
			key := r.Header.Get(idempotencyHeader)
			mu.Lock()
			duplicate := effects[key]
			effects[key] = true
			mu.Unlock()
			if !duplicate {
				w.WriteHeader(http.StatusServiceUnavailable)
				return
			}
		case "/accepted":
			accepted.Add(1)
		case "/rejected":
			rejected.Add(1)
			w.WriteHeader(http.StatusTooManyRequests)
			return
		case "/developer":
			developer.Add(1)
		default:
			disabled.Add(1)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer receiver.Close()
	ok := target("good-app", receiver.URL+"/accepted")
	off := target("disabled-app", receiver.URL+"/disabled")
	off.Enabled = false
	h := startFanout(t, bench, receiver,
		target("ambiguous-app", receiver.URL+"/ambiguous"), ok, ok, off,
		target("bad-app", receiver.URL+"/rejected"), target("", receiver.URL+"/developer"))
	for _, rev := range []string{"1", "2"} {
		enqueue(t, h, rev, "conversation")
		job := h.Settled(rev)
		if job.State != queue.StateCompleted || job.Attempts != 2 ||
			job.Reason == nil || *job.Reason != integrationfanout.CauseDropped {
			t.Fatalf("revision %s: state %s, attempts %d, reason %v", rev, job.State, job.Attempts, job.Reason)
		}
	}
	if accepted.Load() != 2 || rejected.Load() != 2 || developer.Load() != 2 ||
		disabled.Load() != 0 || ambiguous.Load() != 4 {
		t.Fatalf("requests accepted=%d rejected=%d developer=%d disabled=%d ambiguous=%d",
			accepted.Load(), rejected.Load(), developer.Load(), disabled.Load(), ambiguous.Load())
	}
	mu.Lock()
	defer mu.Unlock()
	if len(effects) != 2 || !effects["fanout-revision-1"] || !effects["fanout-revision-2"] {
		t.Fatalf("receiver applied unexpected idempotent effects: %v", effects)
	}
}

func TestFanoutDropsTransientDeliveryOnFinalAttempt(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	var calls atomic.Int32
	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer receiver.Close()
	h := startFanout(t, bench, receiver, target("app", receiver.URL))
	enqueue(t, h, "1", "conversation")
	job := h.Settled("1")
	if job.State != queue.StateCompleted || job.Reason == nil || *job.Reason != integrationfanout.CauseDropped ||
		calls.Load() != int32(queuetest.Policy().MaxAttempts) {
		t.Fatalf("final status %s, reason %v, sends %d", job.State, job.Reason, calls.Load())
	}
}

func TestFanoutSkipsLockedAndDiscardedConversationsAndHoldsDeletingOwner(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	receiver := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Error("receiver called for a suppressed conversation or deleting owner")
	}))
	defer receiver.Close()
	h := startFanout(t, bench, receiver, target("app", receiver.URL), target("", receiver.URL))
	for i, subject := range []string{"locked", "discarded"} {
		key := strconv.Itoa(i + 1)
		enqueue(t, h, key, subject)
		if job := h.Settled(key); job.State != queue.StateCompleted {
			t.Fatalf("%s: state %s", subject, job.State)
		}
	}
	bench.Mark(t, "owner", map[string]any{"wipe_status": "pending"})
	enqueue(t, h, "3", "conversation")
	h.Until("3", "owner deletion is held", func(job queue.Job) bool {
		return job.Reason != nil && *job.Reason == integrationfanout.CauseDeleting
	})
}

func TestReceiptPreservesAcceptanceAndRefusesDeletion(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	g := queue.GuardedForTest(t, "owner", "job")
	s := Receipts{Store: bench.Store}
	id := integrationfanout.Receipt{ConversationID: "conversation", Revision: 1, AppID: "app"}
	for _, disposition := range []integrationfanout.Disposition{integrationfanout.Accepted, integrationfanout.Rejected} {
		if err := s.Record(t.Context(), g, id, disposition); err != nil {
			t.Fatal(err)
		}
	}
	if got, err := s.Read(t.Context(), g, id); err != nil || got != integrationfanout.Accepted {
		t.Fatalf("original receipt changed: %v, %v", got, err)
	}
	bench.Mark(t, "owner", map[string]any{"wipe_status": "pending"})
	id.Revision++
	if err := s.Record(t.Context(), g, id, integrationfanout.Accepted); err == nil {
		t.Fatal("receipt written after deletion began")
	}
	bench.Mark(t, "owner", map[string]any{"wipe_status": "cancelled"})
	if got, err := s.Read(t.Context(), g, id); err != nil || got != 0 {
		t.Fatalf("unexpected receipt after deletion fence: %v, %v", got, err)
	}
}
