package finalization

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const notesFeature = "conv_structure"

type notesWire struct {
	Title    string        `json:"title"`
	Overview string        `json:"overview"`
	Sections []NoteSection `json:"sections"`
}

type sectionKindMode uint8

const (
	sectionKindPreserve sectionKindMode = iota
	sectionKindLegacy
	sectionKindRich
)

func (s *Service) load(ctx context.Context, run *queue.Run, claim Claim) (Conversation, error) {
	var snapshot Conversation
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var err error
		snapshot, err = s.Documents.Load(ctx, g, claim.Intent.Ref)
		return err
	})
	if err != nil {
		return Conversation{}, err
	}
	return snapshot, validateSource(claim, snapshot)
}

func validateSource(claim Claim, snapshot Conversation) error {
	if snapshot.JobID != claim.Intent.JobID || snapshot.Revision != claim.Intent.Revision ||
		(snapshot.Status != rules.Processing && snapshot.Status != rules.Completed) {
		return ErrStale
	}
	return nil
}

func (s *Service) process(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, pending recoveredNotes, claimed *Fanout) error {
	if s.usesServingNotes(claim) && snapshot.SyncMinimumApplied {
		return nil
	}
	if snapshot.Discarded {
		return ErrStale
	}
	if !rules.NeedsNotes(snapshot.Status, snapshot.PendingMinimum) {
		return nil
	}
	snapshot, err := s.waitForEvidence(ctx, run, claim, snapshot)
	if err != nil || !rules.NeedsNotes(snapshot.Status, snapshot.PendingMinimum) {
		return err
	}
	if snapshot.Discarded {
		return ErrStale
	}
	return s.structure(ctx, run, claim, snapshot, pending, claimed)
}

func (s *Service) waitForEvidence(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation) (Conversation, error) {
	var reload bool
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var err error
		reload, err = s.Meeting.Wait(ctx, g, claim, snapshot)
		return err
	})
	if err != nil || !reload {
		return snapshot, err
	}
	return s.load(ctx, run, claim)
}

func (s *Service) structure(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, pending recoveredNotes, claimed *Fanout) error {
	if snapshot.RecordingLayer || snapshot.NoDerivedEffects {
		return s.persist(ctx, run, claim, snapshot, nil, "", "", claimed)
	}
	req, hash, minimum, err := s.prepareNotes(ctx, run, claim, &snapshot)
	if err != nil {
		return err
	}
	if minimum != nil {
		if run.Job().Step == StepNotes {
			// An unconfirmed paid submission must survive the new short-clip decision.
			if !pending.committed {
				return queue.Classify(ErrCompletionAbsent, queue.Yield(CauseStore, time.Minute))
			}
			if snapshot.SyncRevision > pending.operation.SyncRevision {
				return s.deferNotes(ctx, run, claim, pending.operation.SyncRevision, ErrSourceChanged)
			}
			if err := clearNotesOperation(ctx, run); err != nil {
				return err
			}
		}
		return s.persistMinimum(ctx, run, claim, snapshot, minimum, claimed)
	}
	if pending.operation.ID != "" || run.Job().Step == StepNotes {
		return s.resumeNotes(ctx, run, claim, snapshot, req, hash, pending, claimed)
	}
	if reusableNotes(snapshot, hash) {
		return s.persist(ctx, run, claim, snapshot, nil, "", "", claimed)
	}
	return s.submitNotes(ctx, run, claim, snapshot, req, hash, claimed)
}

type emptyDiscardDocuments interface {
	ApplyEmptyDiscard(context.Context, queue.Guarded, Claim, Conversation, Notes) (Fanout, error)
}

func (s *Service) persistMinimum(ctx context.Context, run *queue.Run, claim Claim, before Conversation, minimum *NotesMinimum, claimed *Fanout) error {
	notes := Notes{Title: minimum.Title, Minimum: minimum}
	if documents, ok := s.Documents.(emptyDiscardDocuments); ok && minimum.EmptyTranscriptDiscard() {
		return s.persistEmptyDiscard(ctx, run, claim, before, notes, documents, claimed)
	}
	return s.persist(ctx, run, claim, before, &notes, "", "", claimed)
}

func (s *Service) persistEmptyDiscard(ctx context.Context, run *queue.Run, claim Claim, before Conversation, notes Notes, documents emptyDiscardDocuments, claimed *Fanout) error {
	if before.SourceProjection != nil {
		stabilizeSyncTitle(&notes, before.SourceProjection)
	}
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var err error
		*claimed, err = documents.ApplyEmptyDiscard(ctx, g, claim, before, notes)
		return err
	})
	if errors.Is(err, ErrSourceChanged) {
		return s.deferNotes(ctx, run, claim, before.SyncRevision, err)
	}
	return s.persistError(ctx, run, claim, before.SyncRevision, err)
}

type inlineFanoutDocuments interface {
	ApplyAndClaimFanout(context.Context, queue.Guarded, Claim, Conversation, *Notes, string, string) (Fanout, error)
}

func (s *Service) persist(ctx context.Context, run *queue.Run, claim Claim, before Conversation, notes *Notes, inputHash, outputHash string, claimed *Fanout) error {
	if notes != nil && before.SourceProjection != nil {
		updated := *notes
		stabilizeSyncTitle(&updated, before.SourceProjection)
		notes = &updated
		if inputHash != "" && updated.TitleUpdate != nil {
			var err error
			outputHash, err = canonicalNotes(updated)
			if err != nil {
				return err
			}
		}
	}
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		if documents, ok := s.Documents.(inlineFanoutDocuments); ok && before.InlineFanout {
			var err error
			*claimed, err = documents.ApplyAndClaimFanout(ctx, g, claim, before, notes, inputHash, outputHash)
			return err
		}
		return s.Documents.ApplyFinalization(ctx, g, claim, before, notes, inputHash, outputHash)
	})
	if notes != nil && errors.Is(err, ErrSourceChanged) {
		return s.deferNotes(ctx, run, claim, before.SyncRevision, err)
	}
	return s.persistError(ctx, run, claim, before.SyncRevision, err)
}

func (s *Service) usesServingNotes(claim Claim) bool {
	return s.NotesPrompt != nil && claim.Intent.Trigger == rules.SyncUpdate
}

func (s *Service) prepareNotes(ctx context.Context, run *queue.Run, claim Claim, snapshot *Conversation) (CompletionRequest, string, *NotesMinimum, error) {
	if !s.usesServingNotes(claim) {
		req, hash, err := notesRequest(claim, *snapshot, run.Secret())
		return req, hash, nil, err
	}
	var plan NotesPlan
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var err error
		plan, err = s.NotesPrompt.PrepareNotes(ctx, g, claim, *snapshot)
		return err
	})
	if err != nil {
		return CompletionRequest{}, "", nil, err
	}
	snapshot.SourceProjection = plan.SourceProjection
	snapshot.StampTerminal = plan.StampTerminal
	snapshot.InlineFanout = plan.InlineFanout
	snapshot.openLoopsEnabled = plan.OpenLoopsEnabled
	if plan.Minimum != nil {
		if len(plan.Messages) != 0 || plan.Relevance != nil ||
			(strings.TrimSpace(plan.Minimum.Title) == "" && !plan.Minimum.Discarded) ||
			plan.Minimum.Reason == "" || plan.Minimum.RulesVersion <= 0 {
			return CompletionRequest{}, "", nil, queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
		}
		return CompletionRequest{}, "", plan.Minimum, nil
	}
	if decision := plan.Relevance; decision != nil {
		if decision.Verdict != "keep" || decision.DecidedBy == "" || decision.Reason == "" || decision.RulesVersion <= 0 {
			return CompletionRequest{}, "", nil, queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
		}
		snapshot.Relevance = decision
	}
	snapshot.sectionMode = sectionKindLegacy
	if plan.RichSections {
		snapshot.sectionMode = sectionKindRich
	}
	messages := plan.Messages
	if len(messages) != 2 || messages[0].Role != "system" || messages[1].Role != "user" ||
		strings.TrimSpace(messages[0].Text) == "" || strings.TrimSpace(messages[1].Text) == "" {
		return CompletionRequest{}, "", nil, queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
	}
	// Keep the serialized identity used by already-recorded serving operations.
	type digestMessage struct {
		Role string `json:"Role"`
		Text string `json:"Text"`
	}
	body, err := json.Marshal([2]digestMessage{digestMessage(messages[0]), digestMessage(messages[1])})
	if err != nil {
		return CompletionRequest{}, "", nil, err
	}
	hash := digest(body)
	return CompletionRequest{
		Step: StepNotes + ":serving-text-v1:" + hash, Feature: notesFeature,
		AppPlatform: snapshot.AppPlatform, Messages: messages,
	}, hash, nil, nil
}

type notesInput struct {
	Feature     string        `json:"feature"`
	Prompt      string        `json:"prompt"`
	Transcript  []string      `json:"transcript"`
	AppPlatform string        `json:"app_platform"`
	Trigger     rules.Trigger `json:"trigger"`
}

func notesRequest(claim Claim, snapshot Conversation, secret string) (CompletionRequest, string, error) {
	// This version is independent of the Python dedupe hashes. The prompt and
	// parser versions travel together so a change cannot replay old output.
	// CLEANUP-NOTE(SCA-3181): replace this fixture prompt with the serving prompt policy before rollout.
	const prompt = "Summarize this conversation. Return JSON containing title, overview and sections (an array of section body strings)."
	segments, err := transcriptText(snapshot.Transcript)
	if err != nil {
		return CompletionRequest{}, "", err
	}
	input, err := json.Marshal(notesInput{
		Feature: notesFeature, Prompt: prompt, Transcript: segments,
		Trigger: claim.Intent.Trigger, AppPlatform: snapshot.AppPlatform,
	})
	if err != nil {
		return CompletionRequest{}, "", queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
	}
	hash := digest(input)
	req := CompletionRequest{
		Step: StepNotes + ":json-v1:" + hash, Feature: notesFeature, AppPlatform: snapshot.AppPlatform,
		Messages: []Message{{Role: "system", Text: prompt}, {Role: "user", Text: string(input)}},
	}
	if claim.Intent.RequiresBYOK {
		provider, key, ok := strings.Cut(secret, ":")
		if !ok || provider == "" || key == "" {
			return CompletionRequest{}, "", queue.Classify(ErrInvalid, queue.BlockForSecret())
		}
		req.BYOK = &BYOK{Provider: provider, Key: key}
	}
	return req, hash, nil
}

func transcriptText(segments []json.RawMessage) ([]string, error) {
	texts := make([]string, 0, len(segments))
	for _, segment := range segments {
		var entry struct {
			Text string `json:"text"`
		}
		if json.Unmarshal(segment, &entry) != nil {
			return nil, queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
		}
		if strings.TrimSpace(entry.Text) != "" {
			texts = append(texts, entry.Text)
		}
	}
	return texts, nil
}

func reusableNotes(snapshot Conversation, input string) bool {
	if !snapshot.NotesDedupe || snapshot.NotesInputHash != input || !notesHaveSummary(snapshot.Notes.Overview, snapshot.Notes.Sections) {
		return false
	}
	output, err := canonicalNotes(snapshot.Notes)
	return err == nil && snapshot.NotesOutputHash == output
}

func parseNotes(text string, mode sectionKindMode) (Notes, string, error) {
	var wire notesWire
	if json.Unmarshal([]byte(text), &wire) != nil {
		return Notes{}, "", queue.Classify(errors.New("finalization: unusable notes"), queue.Fail(CauseInvalid))
	}
	for i := range wire.Sections {
		section := &wire.Sections[i]
		switch {
		case mode == sectionKindLegacy:
			section.Kind = ""
		case mode == sectionKindRich && section.Kind == "":
			section.Kind = "main"
		}
	}
	if !notesHaveSummary(wire.Overview, wire.Sections) {
		return Notes{}, "", queue.Classify(errors.New("finalization: unusable notes"), queue.Fail(CauseInvalid))
	}
	notes := Notes{Title: wire.Title, Overview: wire.Overview, Sections: wire.Sections}
	output, err := canonicalNotes(notes)
	return notes, output, err
}

func canonicalNotes(notes Notes) (string, error) {
	body, err := json.Marshal(struct {
		Title    string `json:"title"`
		Overview string `json:"overview"`
		Sections any    `json:"sections"`
	}{notes.Title, notes.Overview, canonicalSections(notes.Sections)})
	if err != nil {
		return "", err
	}
	return digest(body), nil
}

func digest(body []byte) string {
	sum := sha256.Sum256(body)
	return hex.EncodeToString(sum[:])
}
