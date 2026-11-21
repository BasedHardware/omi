package finalization

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

const (
	transcript                  = "synthetic speech never stored in SQL"
	causeTestReject queue.Cause = "test_rejected"
)

func fixture() (*fakePorts, AdmissionRequest) {
	req := AdmissionRequest{Ref: Ref{"owner", "conversation"}, Trigger: rules.CaptureEnd}
	return &fakePorts{
		conversation: Conversation{
			Status: rules.InProgress, Comparison: "initial",
			Transcript: []json.RawMessage{json.RawMessage(`{"text":"` + transcript + `"}`)},
		},
		operations: make(map[string]string),
	}, req
}

func setup(t *testing.T, p *fakePorts, policy queue.Config) (*Service, *queuetest.Harness) {
	t.Helper()
	h := queuetest.Open(t, policy, Declaration(causeTestReject))
	return &Service{
		Queue: h.Store, Outbox: p, Documents: p, Lifecycle: p,
		Meeting: p, Batch: p, Gateway: p, Effects: p, Targets: p, Integrations: p,
	}, h
}

func admit(t *testing.T, s *Service, req AdmissionRequest) Intent {
	t.Helper()
	intent, err := s.Admit(t.Context(), req)
	if err != nil || intent.JobID == "" {
		t.Fatalf("admit: %v, %v", intent, err)
	}
	return intent
}

func settled(t *testing.T, h *queuetest.Harness, intent Intent, want queue.Terminal) queue.Job {
	t.Helper()
	row := h.Settled(intent.JobID)
	if row.Outcome == nil || *row.Outcome != want || len(h.Reports()) != 0 {
		t.Fatalf("job: %+v; want %s; reports %v", row, want, h.Reports())
	}
	return row
}

func TestF01DispatchRefusalPrecedesAdmission(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	req.RequiresDispatch = true
	if _, err := (&Service{Outbox: p}).Admit(t.Context(), req); !errors.Is(err, ErrDispatchUnavailable) {
		t.Fatalf("got %v; want unavailable dispatch", err)
	}
}

func TestF02ConcurrentAdmissionReusesOneIntent(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	s, h := setup(t, p, queuetest.Policy())
	type result struct {
		intent Intent
		err    error
	}
	results := make(chan result, 2)
	for range 2 {
		go func() {
			intent, err := s.Admit(t.Context(), req)
			results <- result{intent, err}
		}()
	}
	first, second := <-results, <-results
	if first.err != nil || second.err != nil || first.intent != second.intent || first.intent.Revision != 1 {
		t.Fatalf("admissions: %+v, %+v", first, second)
	}
	if p.creations != 1 {
		t.Fatalf("created %d intents", p.creations)
	}
	h.Start(map[string]queue.Handler{Kind: s})
	row := settled(t, h, first.intent, queue.TerminalSuccess)
	if strings.Contains(string(row.Meta)+string(row.Checkpoint), transcript) {
		t.Fatal("job stored transcript")
	}
}

func TestF04BYOKWaitsForLiveSecret(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	req.RequiresBYOK = true
	s, h := setup(t, p, queuetest.Policy())
	intent := admit(t, s, req)
	w := h.Start(map[string]queue.Handler{Kind: s})
	row := h.Until(intent.JobID, "blocked for secret", func(job queue.Job) bool { return job.State == queue.StateBlocked })
	if row.Attempts != 0 {
		t.Fatal("gated intent spent a worker claim before resume")
	}
	if err := w.Resume(t.Context(), intent.JobID, "openai:fixture-key"); err != nil {
		t.Fatal(err)
	}
	row = settled(t, h, intent, queue.TerminalSuccess)
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.provider != "openai" || p.paid != 1 || strings.Contains(string(row.Meta)+string(row.Checkpoint), "fixture-key") {
		t.Fatal("BYOK was not passed live or was persisted")
	}
}

func TestF09WaitReloadsTailAndApplyRefusesAChangedSnapshot(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.appendTail, p.changeBeforeApply = true, true
	s, h := setup(t, p, queuetest.Policy())
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	settled(t, h, intent, queue.TerminalSuccess)
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.paid != 2 || p.applied != 1 || !strings.Contains(p.firstPrompt, "late tail") ||
		strings.Contains(p.firstPrompt, "second tail") || !strings.Contains(p.lastPrompt, "second tail") {
		t.Fatal("worker missed a reloaded tail or committed an obsolete revision")
	}
}

func TestF10LostPaidResponseUsesOneOperation(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.losePaidResponse = true
	s, h := setup(t, p, queuetest.Policy())
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	settled(t, h, intent, queue.TerminalSuccess)
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.paid != 1 || p.gatewayCalls != 1 || p.gatewayRecoveries != 1 || p.applied != 1 {
		t.Fatalf("payments %d, calls %d, recoveries %d, writes %d", p.paid, p.gatewayCalls, p.gatewayRecoveries, p.applied)
	}
}

func TestF11DiscardBeforeFanoutFencesEveryDelivery(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.discardBeforeFanout = true
	s, h := setup(t, p, queuetest.Policy())
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	settled(t, h, intent, queue.TerminalFenced)
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.effects != 0 || p.deliveries != 0 || p.fanoutCommitted {
		t.Fatal("discarded revision reached fanout")
	}
}

func TestF14IntegrationRetriesWithRevisionKeyAndDropsOnFinalAttempt(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.integrationTransient = true
	policy := queuetest.Policy()
	policy.MaxAttempts = 2
	s, h := setup(t, p, policy)
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	row := settled(t, h, intent, queue.TerminalSuccess)
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.deliveries < 2 || p.paid != 1 || row.Reason == nil || *row.Reason != CauseDeliveryDropped {
		t.Fatalf("delivery attempts %d, paid notes %d, reason %v", p.deliveries, p.paid, row.Reason)
	}
}

func TestF15CommittedFanoutWinsAtExhaustion(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.loseFanoutResponse = true
	p.dropDelivery = true
	policy := queuetest.Policy()
	policy.MaxAttempts = 1
	s, h := setup(t, p, policy)
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	row := settled(t, h, intent, queue.TerminalSuccess)
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.effects != 1 || p.closedSuccess != 1 || p.deadLetters != 0 || row.Reason == nil || *row.Reason != CauseDeliveryDropped {
		t.Fatal("exhaustion replaced or repeated committed fanout")
	}
}

func TestF16TransientExhaustionGrantsOneBudgetRequeue(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.failGateway = errors.New("gateway unavailable")
	policy := queuetest.Policy()
	policy.MaxAttempts = 1
	s, h := setup(t, p, policy)
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	row := settled(t, h, intent, queue.TerminalFailure)
	p.mu.Lock()
	defer p.mu.Unlock()
	if row.BudgetRequeues != 1 || p.gatewayCalls != 2 || p.deadLetters != 1 {
		t.Fatalf("requeues %d, calls %d, dead letters %d", row.BudgetRequeues, p.gatewayCalls, p.deadLetters)
	}
}

func TestF17DeterministicFailureDoesNotRequeue(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.failGateway = queue.Classify(errors.New("gateway rejected"), queue.Fail(causeTestReject))
	policy := queuetest.Policy()
	policy.MaxAttempts, policy.DeterministicMax = 6, 4
	s, h := setup(t, p, policy)
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	row := settled(t, h, intent, queue.TerminalFailure)
	p.mu.Lock()
	defer p.mu.Unlock()
	if row.BudgetRequeues != 0 || p.gatewayCalls != 4 || p.deadLetters != 1 ||
		p.conversation.Status != rules.Completed || !strings.Contains(string(p.conversation.Transcript[0]), transcript) {
		t.Fatal("dead letter spent a second budget or lost the transcript")
	}
}

func TestF32MissingConversationFencesBeforePaidWork(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.missing = true
	s, h := setup(t, p, queuetest.Policy())
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	settled(t, h, intent, queue.TerminalFenced)
	p.mu.Lock()
	defer p.mu.Unlock()
	if !p.fenced || p.gatewayCalls != 0 || p.deliveries != 0 {
		t.Fatal("missing conversation was not durably fenced or reached a provider")
	}
}

func TestF35OrdinaryPolicyDefaults(t *testing.T) {
	t.Parallel()
	lease, gate, delay, attemptCap := Defaults()
	if lease != 1500*time.Second || gate != 336*time.Hour || delay != 2700*time.Second || attemptCap != 4 || ReconcileStaleness != 300*time.Second {
		t.Fatal("ordinary finalization policy changed")
	}
}

func TestF08AudioOnlyRequiresCustodyBeforeCompletion(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.conversation.Transcript = nil
	p.conversation.Batch = rules.BatchFacts{Owned: true, HasAudio: true}
	s, h := setup(t, p, queuetest.Policy())
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	settled(t, h, intent, queue.TerminalSuccess)
	p.mu.Lock()
	defer p.mu.Unlock()
	if !p.custodyReserved || !p.fanoutCommitted || p.gatewayCalls != 0 {
		t.Fatal("audio-only completion bypassed custody or started paid work")
	}
}

func TestF08ClosedEmptyArchiveFencesWithoutDerivedWork(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	p.conversation.Transcript = nil
	p.conversation.Batch = rules.BatchFacts{Owned: true, ArchiveClosed: true}
	s, h := setup(t, p, queuetest.Policy())
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	settled(t, h, intent, queue.TerminalFenced)
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.custodyReserved || !p.missing || p.gatewayCalls != 0 {
		t.Fatal("empty archive was processed or retained")
	}
}
