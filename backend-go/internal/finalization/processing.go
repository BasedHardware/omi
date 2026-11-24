package finalization

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const notesFeature = "conv_structure"

type notesWire struct {
	Title    string   `json:"title"`
	Overview string   `json:"overview"`
	Sections []string `json:"sections"`
}

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
	if snapshot.JobID != claim.Intent.JobID || snapshot.Revision != claim.Intent.Revision ||
		(snapshot.Status != rules.Processing && snapshot.Status != rules.Completed) {
		return Conversation{}, ErrStale
	}
	return snapshot, nil
}

func (s *Service) process(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, pending recoveredNotes) error {
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
	return s.structure(ctx, run, claim, snapshot, pending)
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

func (s *Service) structure(ctx context.Context, run *queue.Run, claim Claim, snapshot Conversation, pending recoveredNotes) error {
	if snapshot.RecordingLayer || snapshot.NoDerivedEffects {
		return s.persist(ctx, run, claim, snapshot, nil, "", "")
	}
	req, hash, err := notesRequest(claim, snapshot, run.Secret())
	if err != nil {
		return err
	}
	if pending.operation.ID != "" || run.Job().Step == StepNotes {
		return s.resumeNotes(ctx, run, claim, snapshot, req, hash, pending)
	}
	if reusableNotes(snapshot, hash) {
		return s.persist(ctx, run, claim, snapshot, nil, "", "")
	}
	return s.submitNotes(ctx, run, claim, snapshot, req, hash)
}

func (s *Service) persist(ctx context.Context, run *queue.Run, claim Claim, before Conversation, notes *Notes, inputHash, outputHash string) error {
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		return s.Documents.ApplyFinalization(ctx, g, claim, before, notes, inputHash, outputHash)
	})
	if notes != nil && errors.Is(err, ErrSourceChanged) {
		return s.deferNotes(ctx, run, claim, before.SyncRevision, err)
	}
	return s.persistError(ctx, run, claim, before.SyncRevision, err)
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
	if !snapshot.NotesDedupe || snapshot.NotesInputHash != input || !rules.HasSummary(snapshot.Notes.Overview, snapshot.Notes.Sections) {
		return false
	}
	output, err := canonicalNotes(snapshot.Notes)
	return err == nil && snapshot.NotesOutputHash == output
}

func parseNotes(text string) (Notes, string, error) {
	var wire notesWire
	if json.Unmarshal([]byte(text), &wire) != nil || !rules.HasSummary(wire.Overview, wire.Sections) {
		return Notes{}, "", queue.Classify(errors.New("finalization: unusable notes"), queue.Fail(CauseInvalid))
	}
	notes := Notes(wire)
	output, err := canonicalNotes(notes)
	return notes, output, err
}

func canonicalNotes(notes Notes) (string, error) {
	if len(notes.Sections) == 0 {
		notes.Sections = nil
	}
	body, err := json.Marshal(notesWire(notes))
	if err != nil {
		return "", err
	}
	return digest(body), nil
}

func digest(body []byte) string {
	sum := sha256.Sum256(body)
	return hex.EncodeToString(sum[:])
}
