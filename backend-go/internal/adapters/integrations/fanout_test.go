package integrations

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

type finalizer struct {
	service  integrationfanout.Service
	targets  []integrationfanout.Target
	observe  func(integrationfanout.Report)
	disabled func(string) bool
}

func (f finalizer) Work(ctx context.Context, run *queue.Run) queue.Outcome {
	rev, err := strconv.ParseInt(run.Job().Key, 10, 64)
	if err != nil {
		return queue.Fail(integrationfanout.CauseInvalid)
	}
	event := integrationfanout.Event{
		ConversationID: run.Job().Subject, Revision: rev,
		FanoutKey: "conversation:" + run.Job().Subject + ":finalization:" + run.Job().Key,
		Locked:    run.Job().Subject == "locked", Discarded: run.Job().Subject == "discarded",
	}
	targets := append([]integrationfanout.Target(nil), f.targets...)
	if f.disabled != nil {
		for i := range targets {
			targets[i].Disabled = targets[i].Disabled || f.disabled(targets[i].AppID)
		}
	}
	report, err := f.service.Deliver(ctx, run, event, targets)
	if f.observe != nil {
		f.observe(report)
	}
	switch {
	case err != nil:
		return queue.FromError(err, integrationfanout.CauseRetry)
	case report.Dropped:
		return queue.DoneWith(integrationfanout.CauseDropped)
	default:
		return queue.Done()
	}
}

func (finalizer) Exhausted(context.Context, *queue.Reconcile) queue.Resolution { return queue.Park() }

func startFanout(t *testing.T, bench docstoretest.Bench, receiver *httptest.Server, targets ...integrationfanout.Target) *queuetest.Harness {
	t.Helper()
	return startObservedFanout(t, bench, receiver, finalizer{targets: targets})
}

func startObservedFanout(t *testing.T, bench docstoretest.Bench, receiver *httptest.Server, f finalizer) *queuetest.Harness {
	t.Helper()
	h := queuetest.Open(t, queuetest.Policy(), queue.Kind{
		Name: "test_finalization", Formats: []int{1}, Steps: []string{"integrations"}, Causes: integrationfanout.Causes(),
	})
	f.service = integrationfanout.Service{Sender: testSender(t, receiver, 2*time.Second), Receipts: Receipts{Store: bench.Store}}
	h.Start(map[string]queue.Handler{"test_finalization": f})
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
	// The receiver has already processed revision 1 through Python.
	effects := map[string]bool{"conversation:conversation:finalization:1": true}
	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/ambiguous":
			ambiguous.Add(1)
			key := r.Header.Get(appKeyHeader)
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
			w.WriteHeader(http.StatusBadRequest)
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
	for i, rev := range []string{"1", "2"} {
		enqueue(t, h, rev, "conversation")
		job := h.Settled(rev)
		if job.State != queue.StateCompleted || job.Attempts != i+1 ||
			job.Reason == nil || *job.Reason != integrationfanout.CauseDropped {
			t.Fatalf("revision %s: state %s, attempts %d, reason %v", rev, job.State, job.Attempts, job.Reason)
		}
	}
	if accepted.Load() != 2 || rejected.Load() != 2 || developer.Load() != 2 ||
		disabled.Load() != 0 || ambiguous.Load() != 3 {
		t.Fatalf("requests accepted=%d rejected=%d developer=%d disabled=%d ambiguous=%d",
			accepted.Load(), rejected.Load(), developer.Load(), disabled.Load(), ambiguous.Load())
	}
	mu.Lock()
	defer mu.Unlock()
	if len(effects) != 2 || !effects["conversation:conversation:finalization:1"] || !effects["conversation:conversation:finalization:2"] {
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
	requireSchedule(t, h, "3", `SELECT check_after >= updated_at + interval '55 seconds'
FROM queue_tenants JOIN queue_jobs USING (uid) WHERE job_key=$1`)
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
	if got, err := s.Read(t.Context(), g, []integrationfanout.Receipt{id}); err != nil || got[id] != integrationfanout.Accepted {
		t.Fatalf("original receipt changed: %v, %v", got, err)
	}
	bench.Mark(t, "owner", map[string]any{"wipe_status": "pending"})
	id.Revision++
	if err := s.Record(t.Context(), g, id, integrationfanout.Accepted); err == nil {
		t.Fatal("receipt written after deletion began")
	}
	bench.Mark(t, "owner", map[string]any{"wipe_status": "cancelled"})
	if got, err := s.Read(t.Context(), g, []integrationfanout.Receipt{id}); err != nil || len(got) != 0 {
		t.Fatalf("unexpected receipt after deletion fence: %v, %v", got, err)
	}
}

func TestFanoutReportsAttemptsForHealthUsageMessagesAndDeveloperDLQ(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	var disabled atomic.Bool
	var unhealthyCalls atomic.Int32
	var mu sync.Mutex
	var attempts []integrationfanout.Attempt
	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/unhealthy":
			unhealthyCalls.Add(1)
			w.WriteHeader(http.StatusBadRequest)
		case "/developer":
			w.WriteHeader(http.StatusUnauthorized)
		default:
			if _, err := io.WriteString(w, `{"message":"hello from app"}`); err != nil {
				t.Error(err)
			}
		}
	}))
	defer receiver.Close()
	owned := target("owned", receiver.URL+"/owned")
	owned.OwnedByOwner = true
	h := startObservedFanout(t, bench, receiver, finalizer{
		targets: []integrationfanout.Target{
			target("marketplace", receiver.URL+"/marketplace"), owned,
			target("unhealthy", receiver.URL+"/unhealthy"), target("", receiver.URL+"/developer"),
		},
		disabled: func(app string) bool { return app == "unhealthy" && disabled.Load() },
		observe: func(report integrationfanout.Report) {
			mu.Lock()
			defer mu.Unlock()
			for _, attempt := range report.Attempts {
				if attempt.AppID == "unhealthy" && attempt.Failure == integrationfanout.HTTPFailure &&
					attempt.Status == http.StatusBadRequest {
					disabled.Store(true)
				}
				attempts = append(attempts, attempt)
			}
		},
	})
	for _, rev := range []string{"1", "2"} {
		enqueue(t, h, rev, "conversation")
		if job := h.Settled(rev); job.State != queue.StateCompleted || job.Attempts != 1 {
			t.Fatalf("revision %s: state %s, attempts %d", rev, job.State, job.Attempts)
		}
	}
	mu.Lock()
	defer mu.Unlock()
	if len(attempts) != 7 || unhealthyCalls.Load() != 1 {
		t.Fatalf("reported %d attempts, made %d unhealthy calls", len(attempts), unhealthyCalls.Load())
	}
	for _, attempt := range attempts {
		assertAttempt(t, attempt)
	}
}

func assertAttempt(t *testing.T, attempt integrationfanout.Attempt) {
	t.Helper()
	if attempt.ClaimToken <= 0 || attempt.Number != 1 {
		t.Error("missing attempt identity")
	}
	switch attempt.AppID {
	case "":
		if attempt.Status != http.StatusUnauthorized || !attempt.DeadLetter ||
			attempt.RecordUsage || attempt.IdempotencyKey == "" {
			t.Error("missing terminal developer delivery information")
		}
	case "unhealthy":
		if attempt.Status != http.StatusBadRequest || attempt.RecordUsage || attempt.DeadLetter {
			t.Error("missing app health failure")
		}
	case "marketplace", "owned":
		if attempt.Status != http.StatusOK || attempt.RecordUsage != (attempt.AppID == "marketplace") ||
			attempt.Message != "hello from app" || attempt.DeadLetter {
			t.Errorf("missing accepted app usage or message for %s", attempt.AppID)
		}
	default:
		t.Error("unexpected destination")
	}
}

func TestFanoutReportsTransientAttemptAndRechecksDeletionBeforeNextSend(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	results := make(chan integrationfanout.Report, 1)
	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/first" {
			t.Error("second receiver contacted after deletion started")
			return
		}
		_, err := bench.Raw.Collection(docstore.MarkerCollection).Doc("owner").Set(r.Context(), map[string]any{"wipe_status": "pending"})
		if err != nil {
			t.Error(err)
			return
		}
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer receiver.Close()
	h := startObservedFanout(t, bench, receiver, finalizer{
		targets: []integrationfanout.Target{target("app-1", receiver.URL+"/first"), target("app-2", receiver.URL+"/second")},
		observe: func(report integrationfanout.Report) { results <- report },
	})
	enqueue(t, h, "1", "conversation")
	h.Until("1", "owner deletion is held", func(job queue.Job) bool {
		return job.Reason != nil && *job.Reason == integrationfanout.CauseDeleting
	})
	report := <-results
	if len(report.Attempts) != 1 || report.Attempts[0].Disposition != integrationfanout.Transient ||
		report.Attempts[0].Status != http.StatusTooManyRequests || report.Dropped {
		t.Fatal("missing transient attempt in report accompanying the fence error")
	}
}

func TestFanoutRejectsRevisionZero(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	receiver := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Error("receiver called for revision zero")
	}))
	defer receiver.Close()
	h := startFanout(t, bench, receiver, target("app", receiver.URL))
	enqueue(t, h, "0", "conversation")
	if job := h.Settled("0"); job.Outcome == nil || *job.Outcome != queue.TerminalFailure ||
		job.Reason == nil || *job.Reason != integrationfanout.CauseInvalid {
		t.Fatal("invalid revision did not fail deterministically")
	}
}

func TestFanoutUsesRetryAfterFromReceiver(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	receiver := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Retry-After", "45")
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer receiver.Close()
	h := startFanout(t, bench, receiver, target("app", receiver.URL))
	enqueue(t, h, "1", "conversation")
	h.Until("1", "retry with receiver backoff", func(job queue.Job) bool {
		return job.Reason != nil && *job.Reason == integrationfanout.CauseRetry
	})
	requireSchedule(t, h, "1", `SELECT ready_at >= updated_at + interval '44 seconds'
FROM queue_jobs WHERE job_key=$1`)
}

func requireSchedule(t *testing.T, h *queuetest.Harness, key, statement string) {
	t.Helper()
	conn, err := pgx.Connect(t.Context(), h.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if closeErr := conn.Close(t.Context()); closeErr != nil {
			t.Error(closeErr)
		}
	}()
	var scheduled bool
	if err = conn.QueryRow(t.Context(), statement, key).Scan(&scheduled); err != nil {
		t.Fatal(err)
	}
	if !scheduled {
		t.Fatal("job was scheduled before the minimum backoff")
	}
}
