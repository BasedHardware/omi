package finalization

import (
	"context"
	"encoding/json"
	"errors"
	"sync"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type fakePorts struct {
	gatewayRecoveries                                                        int
	fenced                                                                   bool
	integrationTransient                                                     bool
	closedSuccess                                                            int
	custodyReserved                                                          bool
	mu                                                                       sync.Mutex
	intent                                                                   Intent
	conversation                                                             Conversation
	creations, paid, gatewayCalls, applied, effects, deliveries, deadLetters int
	operations                                                               map[string]string
	firstPrompt, lastPrompt, provider                                        string
	appendTail, changeBeforeApply, discardBeforeFanout, missing              bool
	losePaidResponse, loseFanoutResponse, fanoutCommitted, dropDelivery      bool
	failGateway                                                              error
}

func (p *fakePorts) Admit(_ context.Context, a queue.Admitting, req AdmissionRequest, decide func(rules.AdmissionFacts) rules.AdmissionAction) (Intent, error) {
	if err := a.Err(); err != nil {
		return Intent{}, err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	switch decide(rules.AdmissionFacts{Status: p.conversation.Status, HasContent: true, ExistingJob: p.intent.JobID != ""}) {
	case rules.Refuse:
		return Intent{}, nil
	case rules.UseBound:
		return p.intent, nil
	case rules.BindNext:
		p.creations++
		p.intent = Intent{Ref: req.Ref, JobID: JobID(req.Ref, 1), Revision: 1, Trigger: req.Trigger, RequiresBYOK: req.RequiresBYOK}
		p.conversation.Status, p.conversation.JobID, p.conversation.Revision = rules.Processing, p.intent.JobID, 1
	}
	return p.intent, nil
}

func (p *fakePorts) CheckLive(ctx context.Context, g queue.Guarded, intent Intent) error {
	_, err := p.Load(ctx, g, intent.Ref)
	return err
}

func (p *fakePorts) Load(_ context.Context, g queue.Guarded, _ Ref) (Conversation, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.missing {
		return Conversation{}, ErrStale
	}
	return p.conversation, g.Err()
}

func (p *fakePorts) ApplyFinalization(_ context.Context, g queue.Guarded, _ Claim, before Conversation, notes *Notes, input, output string) error {
	if err := g.Err(); err != nil {
		return err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.changeBeforeApply {
		p.changeBeforeApply = false
		p.conversation.Comparison = "after-model"
		p.conversation.Transcript = append(p.conversation.Transcript, json.RawMessage(`{"text":"second tail"}`))
	}
	if p.conversation.Comparison != before.Comparison {
		return queue.Classify(errors.New("changed"), queue.Retry(CauseChanged, 0))
	}
	p.applied++
	p.conversation.Status = rules.Completed
	if notes != nil {
		p.conversation.Notes, p.conversation.NotesInputHash, p.conversation.NotesOutputHash = *notes, input, output
	}
	return nil
}

func (p *fakePorts) Wait(_ context.Context, g queue.Guarded, _ Claim, _ Conversation) (bool, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if !p.appendTail {
		return false, g.Err()
	}
	p.appendTail = false
	p.conversation.Comparison = "after-meeting"
	p.conversation.Transcript = append(p.conversation.Transcript, json.RawMessage(`{"text":"late tail"}`))
	return true, g.Err()
}

func (p *fakePorts) Complete(_ context.Context, g queue.Guarded, req CompletionRequest) (string, error) {
	if err := g.Err(); err != nil {
		return "", err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.gatewayCalls++
	p.lastPrompt = req.Messages[1].Text
	if p.firstPrompt == "" {
		p.firstPrompt = p.lastPrompt
	}
	if req.BYOK != nil {
		p.provider = req.BYOK.Provider
	}
	if p.failGateway != nil {
		return "", p.failGateway
	}
	op := g.Operation(req.Step)
	if existing, ok := p.operations[op]; ok {
		return existing, nil
	}
	p.paid++
	result := `{"title":"Notes","overview":"The summary"}`
	p.operations[op] = result
	if p.losePaidResponse {
		return "", errors.New("lost paid response")
	}
	return result, nil
}

func (*fakePorts) OperationID(g queue.Guarded, step string) string {
	return g.Operation(step)
}

func (p *fakePorts) Recover(_ context.Context, g queue.Guarded, step string) (string, error) {
	if err := g.Err(); err != nil {
		return "", err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.gatewayRecoveries++
	if text, ok := p.operations[g.Operation(step)]; ok {
		return text, nil
	}
	return "", ErrCompletionAbsent
}

func (p *fakePorts) Begin(_ context.Context, g queue.Guarded, _ Claim) error {
	return g.Err()
}

func (p *fakePorts) ClaimFanout(_ context.Context, g queue.Guarded, claim Claim) (Fanout, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.discardBeforeFanout {
		p.conversation.Discarded = true
	}
	if p.conversation.Discarded || p.conversation.JobID != claim.Intent.JobID || p.conversation.Status != rules.Completed {
		return Fanout{State: FanoutStale}, g.Err()
	}
	return Fanout{State: FanoutAcquired, Key: "fixture-revision-fanout", Conversation: p.conversation}, g.Err()
}

func (p *fakePorts) CompleteFanout(_ context.Context, g queue.Guarded, _ Claim, dropped bool) error {
	if err := g.Err(); err != nil {
		return err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.fanoutCommitted = true
	p.dropDelivery = dropped
	if p.loseFanoutResponse {
		return errors.New("lost fanout response")
	}
	return nil
}

func (p *fakePorts) ReconcileCompletion(_ context.Context, g queue.Guarded, _ Claim) (TerminalState, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.fanoutCommitted && p.closedSuccess == 0 {
		p.closedSuccess++
	}
	switch {
	case p.fanoutCommitted && p.dropDelivery:
		return TerminalDeliveryDropped, g.Err()
	case p.fanoutCommitted:
		return TerminalComplete, g.Err()
	default:
		return TerminalPending, g.Err()
	}
}

func (p *fakePorts) Fence(_ context.Context, g queue.Guarded, _ Claim) (TerminalState, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.fenced = true
	return TerminalStale, g.Err()
}

func (p *fakePorts) DeadLetter(_ context.Context, g queue.Guarded, _ Claim, _ queue.Cause, _ bool) (TerminalState, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.deadLetters++
	p.conversation.Status = rules.Completed
	return TerminalDeadLetter, g.Err()
}

func (p *fakePorts) Apply(_ context.Context, g queue.Guarded, _ Claim, _ Fanout, _ rules.Effects) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.effects++
	return g.Err()
}

func (p *fakePorts) Resolve(_ context.Context, g queue.Guarded, _ Claim, _ Conversation) ([]Target, error) {
	return []Target{{Enabled: true, Created: true}}, g.Err()
}

func (p *fakePorts) Deliver(_ context.Context, g queue.Guarded, event IntegrationEvent, _ []Target, budget DeliveryBudget) (bool, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if event.FanoutKey != "fixture-revision-fanout" {
		return false, errors.New("incorrect fanout key")
	}
	p.deliveries++
	if p.integrationTransient && !budget.Final {
		return false, queue.Classify(errors.New("fixture receiver timed out"), queue.Retry(causeTestReject, 0))
	}
	return p.dropDelivery || p.integrationTransient, g.Err()
}

func (p *fakePorts) Reserve(_ context.Context, g queue.Guarded, _ Claim, _ Conversation) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.custodyReserved = true
	return g.Err()
}

func (p *fakePorts) CompleteCapture(_ context.Context, g queue.Guarded, _ Claim, _ Conversation) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if !p.custodyReserved && !p.conversation.Discarded {
		return errors.New("batch custody was not reserved")
	}
	p.fanoutCommitted = true
	p.conversation.Status = rules.Completed
	return g.Err()
}

func (p *fakePorts) DeleteEmpty(_ context.Context, g queue.Guarded, _ Claim, _ Conversation) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if !p.conversation.Batch.ArchiveClosed || p.conversation.Batch.HasAudio {
		return errors.New("archive is not proven empty")
	}
	p.missing = true
	return g.Err()
}
