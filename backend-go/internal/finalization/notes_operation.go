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
		if err := s.Documents.CheckLive(ctx, g, claim.Intent); err != nil {
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

func (s *Service) resumeNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, req CompletionRequest, hash string, pending recoveredNotes) error {
	op := pending.operation
	if op.ID == "" {
		return s.recoverLegacyNotes(ctx, run, claim, snapshot, req, hash)
	}
	if op.InputHash == hash {
		if pending.committed {
			return s.applyNotes(ctx, run, claim, snapshot, pending.text, hash)
		}
		req.Step = op.Step
		return s.postNotes(ctx, run, claim, snapshot, req, hash)
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

func (s *Service) recoverLegacyNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, req CompletionRequest, hash string) error {
	var text string
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		if err := s.Documents.CheckLive(ctx, g, claim.Intent); err != nil {
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
	return s.applyNotes(ctx, run, claim, snapshot, text, hash)
}

func (s *Service) submitNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, req CompletionRequest, hash string) error {
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
	return s.postNotes(ctx, run, claim, snapshot, req, hash)
}

func (s *Service) postNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, req CompletionRequest, hash string) error {
	req.JobCreatedAt = run.Job().CreatedAt
	var text string
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		if err := s.Documents.CheckLive(ctx, g, claim.Intent); err != nil {
			return err
		}
		var callErr error
		text, callErr = s.Gateway.Complete(ctx, g, req)
		return callErr
	})
	if err != nil {
		return err
	}
	return s.applyNotes(ctx, run, claim, snapshot, text, hash)
}

func (s *Service) applyNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, text, hash string) error {
	notes, output, err := parseNotes(text)
	if err != nil {
		return err
	}
	return s.persist(ctx, run, claim, snapshot, &notes, hash, output)
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
