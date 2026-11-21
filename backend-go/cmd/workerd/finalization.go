package main

import (
	"context"
	"errors"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/finalizationdocs"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/objectlake"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// wireFinalizationDocuments connects the ordinary family to the merged
// conversation port and the finalization lifecycle store. Registration still
// requires the serving gateway and the remaining effect ports.
func wireFinalizationDocuments(service *finalization.Service, store finalizationdocs.Store, offload conversations.TranscriptReader, notesDedupe bool) {
	service.Outbox = store
	service.Lifecycle = store
	service.Replay = store
	service.Quiet = store
	service.EpisodeIntake = store
	service.Summaries = store
	service.Documents = finalizationDocuments{store: conversations.Store{Docs: store.Docs, Codec: store.Codec, Offload: offload}, notesDedupe: notesDedupe}
}

type finalizationDocuments struct {
	store       conversations.Store
	notesDedupe bool
}

func (f finalizationDocuments) CheckLive(ctx context.Context, g queue.Guarded, intent finalization.Intent) error {
	ref := conversations.Ref{Owner: intent.Ref.Owner, ID: intent.Ref.ID}
	err := f.store.CheckLive(ctx, g, ref, intent.JobID, intent.Revision)
	if errors.Is(err, docstore.ErrMissing) || errors.Is(err, conversations.ErrRestricted) {
		return finalization.ErrStale
	}
	return err
}

func (f finalizationDocuments) Load(ctx context.Context, g queue.Guarded, ref finalization.Ref) (finalization.Conversation, error) {
	row, err := f.store.Load(ctx, g, conversations.Ref{Owner: ref.Owner, ID: ref.ID})
	if errors.Is(err, docstore.ErrMissing) || errors.Is(err, conversations.ErrRestricted) || errors.Is(err, objectlake.ErrRestricted) {
		return finalization.Conversation{}, finalization.ErrStale
	}
	return finalization.Conversation{
		Comparison: row.Revision, Status: rules.Status(row.Status), JobID: row.FinalizationJobID,
		Revision: row.FinalizationRevision, SyncRevision: row.SyncContentRevision,
		Transcript: row.Transcript, Discarded: row.Discarded,
		Notes:       finalization.Notes{Title: row.Title, Overview: row.Overview, Sections: row.Sections},
		NotesDedupe: f.notesDedupe, NotesInputHash: row.NotesInputHash, NotesOutputHash: row.NotesOutputHash,
	}, err
}

func (f finalizationDocuments) ApplyFinalization(ctx context.Context, g queue.Guarded, _ finalization.Claim, before finalization.Conversation, notes *finalization.Notes, inputHash, outputHash string) error {
	revision, ok := before.Comparison.(conversations.Revision)
	if !ok {
		return finalization.ErrInvalid
	}
	status := conversations.Completed
	patch := conversations.Finalization{Status: &status}
	if notes != nil {
		patch.Title, patch.Overview, patch.Sections = &notes.Title, &notes.Overview, &notes.Sections
		patch.NotesInputHash, patch.NotesOutputHash = &inputHash, &outputHash
	}
	err := f.store.ApplyFinalization(ctx, g, revision, patch)
	switch {
	case errors.Is(err, conversations.ErrChanged):
		return finalization.ErrSourceChanged
	case errors.Is(err, docstore.ErrMissing), errors.Is(err, conversations.ErrRestricted), errors.Is(err, conversations.ErrLifecycleRefused):
		return finalization.ErrStale
	default:
		return err
	}
}
