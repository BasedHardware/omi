package main

import (
	"context"
	"errors"

	"strings"
	"sync"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/finalizationdocs"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

type syntheticEffects struct{}

func (syntheticEffects) Wait(_ context.Context, g queue.Guarded, _ finalization.Claim, _ finalization.Conversation) (bool, error) {
	return false, g.Err()
}

func (syntheticEffects) Apply(_ context.Context, g queue.Guarded, _ finalization.Claim, _ finalization.Fanout, _ rules.Effects) error {
	return g.Err()
}

func (syntheticEffects) Resolve(_ context.Context, g queue.Guarded, _ finalization.Claim, _ finalization.Conversation) ([]finalization.Target, error) {
	return nil, g.Err()
}

func (syntheticEffects) Reserve(_ context.Context, g queue.Guarded, _ finalization.Claim, _ finalization.Conversation) error {
	return g.Err()
}

func (syntheticEffects) CompleteCapture(_ context.Context, g queue.Guarded, _ finalization.Claim, _ finalization.Conversation) error {
	return g.Err()
}

func (syntheticEffects) DeleteEmpty(_ context.Context, g queue.Guarded, _ finalization.Claim, _ finalization.Conversation) error {
	return g.Err()
}

func (syntheticEffects) Deliver(_ context.Context, g queue.Guarded, _ finalization.IntegrationEvent, _ []finalization.Target, _ finalization.DeliveryBudget) (bool, error) {
	return false, g.Err()
}

type syntheticGateway struct {
	first                 sync.Once
	beforeFirstCompletion func(context.Context) error
}

func (s *syntheticGateway) Complete(ctx context.Context, g queue.Guarded, req finalization.CompletionRequest) (string, error) {
	if err := g.Err(); err != nil {
		return "", err
	}
	if req.JobCreatedAt.IsZero() {
		return "", finalization.ErrInvalid
	}
	var first bool
	var firstErr error
	s.first.Do(func() {
		first = true
		firstErr = s.beforeFirstCompletion(ctx)
	})
	if first {
		return `{"title":"Obsolete", "overview":"Stale summary"}`, firstErr
	}
	if !strings.Contains(req.Messages[1].Text, "late speech") {
		return "", finalization.ErrInvalid
	}
	return `{"title":"Latest", "overview":"Summary includes late speech","sections":["Synthetic detail"]}`, nil
}

func (*syntheticGateway) OperationID(g queue.Guarded, step string) string {
	return g.Operation(step)
}

func (*syntheticGateway) Recover(context.Context, queue.Guarded, string) (string, error) {
	return "", finalization.ErrCompletionAbsent
}

func TestF09MergedDocumentAdapterFencesNewerInputAndUpdatesHome(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	const path = "users/replay-owner/conversations/replay-conversation"
	row := map[string]any{
		"status": "in_progress", "user_title": "Owner's title",
		"sync_content_revision": int64(1), "transcript_segments": []map[string]any{{"text": "initial speech"}},
	}
	if _, err := bench.Raw.Doc(path).Set(t.Context(), row); err != nil {
		t.Fatal(err)
	}
	h := queuetest.Open(t, queuetest.Policy(), workerdKinds()...)
	lifecycle := finalizationdocs.Store{Docs: bench.Store, Clock: clock.System{}}
	effects := syntheticEffects{}
	s := &finalization.Service{
		Queue:   h.Store,
		Meeting: effects, Effects: effects, Targets: effects, Batch: effects, Integrations: effects,
		Gateway: &syntheticGateway{beforeFirstCompletion: func(ctx context.Context) error {
			current, err := bench.Raw.Doc(path).Get(ctx)
			if err != nil {
				return err
			}
			fields := current.Data()
			fields["sync_content_revision"] = int64(2)
			fields["transcript_segments"] = []map[string]any{{"text": "initial speech"}, {"text": "late speech"}}
			_, err = bench.Raw.Doc(path).Set(ctx, fields)
			return err
		}},
	}
	wireFinalizationDocuments(s, lifecycle, nil, true)
	intent, err := s.Admit(t.Context(), finalization.AdmissionRequest{
		Ref: finalization.Ref{Owner: "replay-owner", ID: "replay-conversation"}, Trigger: rules.CaptureEnd,
	})
	if err != nil || intent.JobID == "" {
		t.Fatalf("admit: %+v %v", intent, err)
	}
	handlers := workerdHandlers(s)
	if handlers[finalization.Kind] != s {
		t.Fatal("fully composed finalization handler was not registered")
	}
	h.Start(handlers)
	waiting := h.Until(intent.JobID, "sync revision quiet wait", func(job queue.Job) bool {
		return job.State == queue.StateWaiting && job.Reason != nil && *job.Reason == finalization.CauseChanged
	})
	if waiting.Attempts != 0 {
		t.Fatalf("sync yield spent an attempt: %+v", waiting)
	}
	job := h.Settled(intent.JobID)
	if job.Outcome == nil || *job.Outcome != queue.TerminalSuccess || job.Attempts != 1 {
		t.Fatalf("job: %+v; reports %v", job, h.Reports())
	}
	conv, err := bench.Raw.Doc(path).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	var fields struct {
		Status     string `firestore:"status"`
		Structured struct {
			Title    string `firestore:"title"`
			Overview string `firestore:"overview"`
			Sections []struct {
				Body string `firestore:"body_markdown"`
			} `firestore:"sections"`
		} `firestore:"structured"`
		InputHash  string `firestore:"go_finalization_notes_input_hash"`
		OutputHash string `firestore:"go_finalization_notes_output_hash"`
	}
	if err := conv.DataTo(&fields); err != nil {
		t.Fatal(err)
	}
	if len(fields.Structured.Sections) != 1 || fields.Structured.Sections[0].Body != "Synthetic detail" ||
		len(fields.InputHash) != 64 || len(fields.OutputHash) != 64 {
		t.Fatal("generated sections and hashes did not commit together")
	}
	if fields.Status != "completed" || fields.Structured.Title != "Owner's title" ||
		fields.Structured.Overview != "Summary includes late speech" ||
		!bench.Exists(t, "users/replay-owner/episode_links/replay-conversation") {
		t.Fatalf("stale input committed or Home receipt missing: %+v", fields)
	}
}

type unavailableNotes struct{}

func (unavailableNotes) Complete(context.Context, queue.Guarded, finalization.CompletionRequest) (string, error) {
	return "", errors.New("synthetic provider outage")
}

func (unavailableNotes) OperationID(g queue.Guarded, step string) string {
	return g.Operation(step)
}

func (unavailableNotes) Recover(context.Context, queue.Guarded, string) (string, error) {
	return "", finalization.ErrCompletionAbsent
}

func TestF35ManualRedriveResumesFanoutWithoutAnotherAutomaticGrant(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	ref := finalization.Ref{Owner: "redrive-owner", ID: "redrive-conversation"}
	path := "users/" + ref.Owner + "/conversations/" + ref.ID
	if _, err := bench.Raw.Doc(path).Set(t.Context(), map[string]any{
		"status": "in_progress", "transcript_segments": []map[string]any{{"text": "retained conversation"}},
	}); err != nil {
		t.Fatal(err)
	}
	policy := queuetest.Policy()
	policy.MaxAttempts = 1
	causes := append(finalizationdocs.Causes(), conversations.Causes()...)
	h := queuetest.Open(t, policy, finalization.Declaration(causes...))
	effects := syntheticEffects{}
	s := &finalization.Service{Queue: h.Store, Meeting: effects, Effects: effects, Targets: effects, Gateway: unavailableNotes{}}
	wireFinalizationDocuments(s, finalizationdocs.Store{Docs: bench.Store, Clock: clock.System{}}, nil, true)
	intent, err := s.Admit(t.Context(), finalization.AdmissionRequest{Ref: ref, Trigger: rules.CaptureEnd})
	if err != nil {
		t.Fatal(err)
	}
	h.Start(map[string]queue.Handler{finalization.Kind: s})
	failed := h.Settled(intent.JobID)
	if failed.Outcome == nil || *failed.Outcome != queue.TerminalFailure || failed.BudgetRequeues != 1 {
		t.Fatalf("expected one spent budget: %+v", failed)
	}
	if staleErr := s.Redrive(t.Context(), intent, failed.Token+1); !errors.Is(staleErr, queue.ErrState) {
		t.Fatalf("redrive with wrong epoch: %v", staleErr)
	}

	if redriveErr := s.Redrive(t.Context(), intent, failed.Token); redriveErr != nil {
		t.Fatal(redriveErr)
	}
	settled := h.Settled(intent.JobID)
	if settled.Outcome == nil || *settled.Outcome != queue.TerminalSuccess || settled.BudgetRequeues != 1 || settled.Attempts != 1 {
		t.Fatalf("expected redriven fanout with preserved budget: %+v", settled)
	}
}
