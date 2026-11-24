package finalization

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// notesOperation records the gateway identity and input fingerprint before a paid POST.
type notesOperation struct {
	ID           string `json:"id"`
	Step         string `json:"step"`
	InputHash    string `json:"input_hash"`
	SyncRevision int64  `json:"sync_revision"`
}

type recoveredNotes struct {
	operation notesOperation
	text      string
	committed bool
}

func (s *Service) recoverNotes(ctx context.Context, run *queue.Run, claim Claim) (recoveredNotes, error) {
	var pending recoveredNotes
	job := run.Job()
	if job.Step != StepNotes || len(job.Checkpoint) == 0 || string(job.Checkpoint) == "null" {
		return pending, nil
	}
	op := &pending.operation
	if json.Unmarshal(job.Checkpoint, op) != nil || op.ID == "" || op.Step == "" || op.InputHash == "" {
		return pending, queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
	}
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		if s.Gateway.OperationID(g, op.Step) != op.ID {
			return queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
		}
		if err := s.Documents.CheckNotesRecovery(ctx, g, claim.Intent); err != nil {
			return err
		}
		text, err := s.Gateway.Recover(ctx, g, op.Step)
		pending.text, pending.committed = text, err == nil
		return err
	})
	if errors.Is(err, ErrCompletionAbsent) {
		return pending, nil
	}
	return pending, err
}

func (s *Service) resumeNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, req CompletionRequest, hash string, pending recoveredNotes, claimed *Fanout) error {
	op := pending.operation
	if op.ID == "" {
		return s.recoverLegacyNotes(ctx, run, claim, snapshot, req, hash, claimed)
	}
	if op.InputHash == hash {
		if pending.committed {
			return s.applyNotes(ctx, run, claim, snapshot, pending.text, hash, claimed)
		}
		req.Step = op.Step
		return s.postNotes(ctx, run, claim, snapshot, req, hash, claimed)
	}
	if !pending.committed {
		// The gateway's absence result includes indeterminate and expired claims.
		// Without the original prompt, the old operation cannot safely be resubmitted.
		return queue.Classify(ErrCompletionAbsent, queue.Retry(CauseStore, 0))
	}
	if snapshot.SyncRevision > op.SyncRevision {
		return s.deferNotes(ctx, run, claim, op.SyncRevision, ErrSourceChanged)
	}
	if err := clearNotesOperation(ctx, run); err != nil {
		return err
	}
	return queue.Classify(ErrSourceChanged, queue.Retry(CauseChanged, 0))
}

func (s *Service) recoverLegacyNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, req CompletionRequest, hash string, claimed *Fanout) error {
	var text string
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		if err := s.Documents.CheckNotesRecovery(ctx, g, claim.Intent); err != nil {
			return err
		}
		var callErr error
		text, callErr = s.Gateway.Recover(ctx, g, req.Step)
		return callErr
	})
	if errors.Is(err, ErrCompletionAbsent) {
		// Older jobs saved only the phase. A different input may already have been paid for.
		return queue.Classify(err, queue.Fail(CauseInvalid))
	}
	if err != nil {
		return err
	}
	return s.applyNotes(ctx, run, claim, snapshot, text, hash, claimed)
}

func (s *Service) submitNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, req CompletionRequest, hash string, claimed *Fanout) error {
	op := notesOperation{Step: req.Step, InputHash: hash, SyncRevision: snapshot.SyncRevision}
	err := run.Guard(ctx, func(_ context.Context, g queue.Guarded) error {
		op.ID = s.Gateway.OperationID(g, op.Step)
		return g.Err()
	})
	if err != nil {
		return err
	}
	checkpoint, err := json.Marshal(op)
	if err != nil {
		return err
	}
	if saveErr := run.Save(ctx, StepNotes, checkpoint); saveErr != nil {
		return saveErr
	}
	return s.postNotes(ctx, run, claim, snapshot, req, hash, claimed)
}

func (s *Service) postNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, req CompletionRequest, hash string, claimed *Fanout) error {
	req.JobCreatedAt = run.Job().CreatedAt
	var syncRevision int64
	if s.usesServingNotes(claim) {
		syncRevision = snapshot.SyncRevision
	}
	var text string
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		if err := s.Documents.CheckLive(ctx, g, claim.Intent, syncRevision); err != nil {
			return err
		}
		var callErr error
		text, callErr = s.Gateway.Complete(ctx, g, req)
		return callErr
	})
	if err != nil {
		return err
	}
	return s.applyNotes(ctx, run, claim, snapshot, text, hash, claimed)
}

func (s *Service) applyNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, text, hash string, claimed *Fanout) error {
	notes, _, err := parseNotes(text, snapshot.sectionMode)
	if err != nil {
		return err
	}
	notes.keepEvidenceFrom(snapshot.Transcript)
	if actionErr := s.prepareNoteActions(ctx, run, claim, snapshot, text, &notes); actionErr != nil {
		return actionErr
	}
	if snapshot.openLoopsEnabled {
		notes.OpenLoops = parseSyncOpenLoops(text)
	}
	output, err := canonicalNotes(notes)
	if err != nil {
		return err
	}
	return s.persist(ctx, run, claim, snapshot, &notes, hash, output, claimed)
}

type notesActionValidator interface {
	ValidateActions(context.Context, queue.Guarded, Claim, Conversation, []json.RawMessage) ([]map[string]any, error)
}

func (s *Service) prepareNoteActions(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, text string, notes *Notes) error {
	validator, enabled := s.NotesPrompt.(notesActionValidator)
	if !enabled || !s.usesServingNotes(claim) {
		return nil
	}
	var payload struct {
		Actions []json.RawMessage `json:"action_items"`
	}
	if err := json.Unmarshal([]byte(text), &payload); err != nil || len(payload.Actions) > 64 {
		return queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
	}
	if payload.Actions == nil {
		return nil
	}
	if len(payload.Actions) == 0 {
		notes.ActionItems = &[]map[string]any{}
		return nil
	}
	return run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		actions, err := validator.ValidateActions(ctx, g, claim, snapshot, payload.Actions)
		if err == nil {
			notes.ActionItems = &actions
		}
		return err
	})
}

func (s *Service) deferNotes(ctx context.Context, run *queue.Run, claim Claim, revision int64, changed error) error {
	delay, err := s.deferSyncRevision(ctx, run, claim, revision)
	if err != nil {
		return err
	}
	if err := clearNotesOperation(ctx, run); err != nil {
		return err
	}
	return queue.Classify(changed, queue.Yield(CauseChanged, delay))
}

func clearNotesOperation(ctx context.Context, run *queue.Run) error {
	return run.Save(ctx, StepLoad, json.RawMessage("null"))
}
