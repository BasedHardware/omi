package finalizationintegration_test

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
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

// This composition belongs with the runtime wiring once its remaining ports
// are available. The test calls the merged lane 2 port with its own opaque
// revision and exercises the lane 6 admission, claim and terminal transactions.
type conversationFixture struct{ store conversations.Store }

func (f conversationFixture) Load(ctx context.Context, g queue.Guarded, ref finalization.Ref) (finalization.Conversation, error) {
	row, err := f.store.Load(ctx, g, conversations.Ref{Owner: ref.Owner, ID: ref.ID})
	if errors.Is(err, docstore.ErrMissing) {
		return finalization.Conversation{}, finalization.ErrStale
	}
	return finalization.Conversation{
		Comparison: row.Revision, Status: rules.Status(row.Status), JobID: row.FinalizationJobID,
		Revision: row.FinalizationRevision, SyncRevision: row.SyncContentRevision,
		Transcript: row.Transcript, Discarded: row.Discarded,
	}, err
}

func (f conversationFixture) ApplyFinalization(ctx context.Context, g queue.Guarded, _ finalization.Claim, before finalization.Conversation, notes *finalization.Notes, _, _ string) error {
	revision, ok := before.Comparison.(conversations.Revision)
	if !ok {
		return finalization.ErrInvalid
	}
	status := conversations.Completed
	patch := conversations.Finalization{Status: &status}
	// The merged field patch accepts the fixture's title and overview. The notes
	// sections and dedupe hashes still need a write surface in the real adapter.
	if notes != nil {
		if len(notes.Sections) != 0 {
			return finalization.ErrInvalid
		}
		patch.Title, patch.Overview = &notes.Title, &notes.Overview
	}
	return f.store.ApplyFinalization(ctx, g, revision, patch)
}

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
	return `{"title":"Latest", "overview":"Summary includes late speech"}`, nil
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
	causes := append(finalizationdocs.Causes(), conversations.Causes()...)
	h := queuetest.Open(t, queuetest.Policy(), finalization.Declaration(causes...))
	lifecycle := finalizationdocs.Store{Docs: bench.Store, Clock: clock.System{}}
	processor := conversationFixture{store: conversations.Store{Docs: bench.Store}}
	effects := syntheticEffects{}
	s := &finalization.Service{
		Queue: h.Store, Outbox: lifecycle, Lifecycle: lifecycle, Documents: processor,
		Meeting: effects, Effects: effects, Targets: effects,
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
	intent, err := s.Admit(t.Context(), finalization.AdmissionRequest{
		Ref: finalization.Ref{Owner: "replay-owner", ID: "replay-conversation"}, Trigger: rules.CaptureEnd,
	})
	if err != nil || intent.JobID == "" {
		t.Fatalf("admit: %+v %v", intent, err)
	}
	h.Start(map[string]queue.Handler{finalization.Kind: s})
	job := h.Settled(intent.JobID)
	if job.Outcome == nil || *job.Outcome != queue.TerminalSuccess || job.Attempts != 2 {
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
		} `firestore:"structured"`
	}
	if err := conv.DataTo(&fields); err != nil {
		t.Fatal(err)
	}
	if fields.Status != "completed" || fields.Structured.Title != "Owner's title" ||
		fields.Structured.Overview != "Summary includes late speech" ||
		!bench.Exists(t, "users/replay-owner/episode_links/replay-conversation") {
		t.Fatalf("stale input committed or Home receipt missing: %+v", fields)
	}
}
