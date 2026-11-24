package main

import (
	"context"
	"errors"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/finalizationdocs"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
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
	service.Documents = finalizationDocuments{
		jobs:        store,
		store:       conversations.Store{Docs: store.Docs, Codec: store.Codec, Offload: offload},
		notesDedupe: notesDedupe,
		syncOnly:    store.SyncOnly,
		clock:       store.Clock,
	}
}

type finalizationDocuments struct {
	jobs        finalizationdocs.Store
	store       conversations.Store
	notesDedupe bool
	syncOnly    bool
	clock       clock.Clock
}

func (f finalizationDocuments) CheckLive(ctx context.Context, g queue.Guarded, intent finalization.Intent, syncRevision int64) error {
	ref := conversations.Ref{Owner: intent.Ref.Owner, ID: intent.Ref.ID}
	err := f.store.CheckLive(ctx, g, ref, intent.JobID, intent.Revision, syncRevision)
	return classifyNotesSource(err)
}

func (f finalizationDocuments) CheckNotesRecovery(ctx context.Context, g queue.Guarded, intent finalization.Intent) error {
	if !f.syncOnly {
		return f.CheckLive(ctx, g, intent, 0)
	}
	ref := conversations.Ref{Owner: intent.Ref.Owner, ID: intent.Ref.ID}
	return classifyNotesSource(f.store.CheckSyncNotesRecoverySource(ctx, g, ref, intent.JobID, intent.Revision))
}

func classifyNotesSource(err error) error {
	if errors.Is(err, docstore.ErrMissing) || errors.Is(err, conversations.ErrRestricted) {
		return finalization.ErrStale
	}
	return err
}

func (f finalizationDocuments) Load(ctx context.Context, g queue.Guarded, ref finalization.Ref) (finalization.Conversation, error) {
	row, err := f.store.Load(ctx, g, conversations.Ref{Owner: ref.Owner, ID: ref.ID})
	return f.conversation(row, err)
}

func (f finalizationDocuments) BeginSync(ctx context.Context, g queue.Guarded, claim finalization.Claim) (finalization.Conversation, bool, error) {
	reconcile, source, err := f.jobs.BeginSync(ctx, g, claim)
	if err != nil || reconcile {
		return finalization.Conversation{}, reconcile, err
	}
	ref := conversations.Ref{Owner: claim.Intent.Ref.Owner, ID: claim.Intent.Ref.ID}
	row, err := f.store.DecodeFencedSnapshot(ctx, g, ref, source)
	snapshot, err := f.conversation(row, err)
	return snapshot, false, err
}

func (f finalizationDocuments) conversation(row conversations.Conversation, err error) (finalization.Conversation, error) {
	if errors.Is(err, docstore.ErrMissing) || errors.Is(err, conversations.ErrRestricted) || errors.Is(err, objectlake.ErrRestricted) {
		return finalization.Conversation{}, finalization.ErrStale
	}
	return finalization.Conversation{
		Comparison: row.Revision, Status: rules.Status(row.Status), JobID: row.FinalizationJobID,
		Revision: row.FinalizationRevision, SyncRevision: row.SyncContentRevision,
		Transcript: row.Transcript, Discarded: row.Discarded,
		AppPlatform: row.AppPlatform, RecordingLayer: row.RecordingLayer, NoDerivedEffects: row.NoDerivedEffects,
		UntrustedCapture: row.UntrustedCapture, PendingMinimum: row.PendingMinimum, SyncMinimumApplied: row.SyncMinimumApplied,
		Batch:       rules.BatchFacts{Owned: row.BatchOwned, HasAudio: row.HasAudio, HasPhotos: row.HasPhotos},
		Notes:       finalization.Notes{Title: row.Title, Overview: row.Overview, Sections: row.Sections},
		NotesDedupe: f.notesDedupe, NotesInputHash: row.NotesInputHash, NotesOutputHash: row.NotesOutputHash,
	}, err
}

func (f finalizationDocuments) ApplyFinalization(ctx context.Context, g queue.Guarded, _ finalization.Claim, before finalization.Conversation, notes *finalization.Notes, inputHash, outputHash string) error {
	revision, ok := before.Comparison.(conversations.Revision)
	if !ok {
		return finalization.ErrInvalid
	}
	patch, err := f.finalizationPatch(before, notes, inputHash, outputHash)
	if err != nil {
		return err
	}
	return finalizationWriteError(f.store.ApplyFinalization(ctx, g, revision, patch))
}

func (f finalizationDocuments) ApplyEmptyDiscard(ctx context.Context, g queue.Guarded, claim finalization.Claim, before finalization.Conversation, notes finalization.Notes) (finalization.Fanout, error) {
	revision, ok := before.Comparison.(conversations.Revision)
	if !f.syncOnly || !ok || notes.Minimum == nil || !notes.Minimum.EmptyTranscriptDiscard() {
		return finalization.Fanout{}, finalization.ErrInvalid
	}
	patch, err := f.finalizationPatch(before, &notes, "", "")
	if err != nil {
		return finalization.Fanout{}, err
	}
	// The encrypted card is sent by receivers that understand the row-bound
	// fanout claim. Older receivers continue to read the job's fanout marker.
	inline := before.SourceProjection != nil && before.SourceProjection.EmptyDiscardHome != nil
	if inline {
		patch.EmptyDiscardFanoutEpoch = claim.Epoch
	}
	return f.commitFanout(ctx, g, claim, revision, patch, inline, true)
}

func (f finalizationDocuments) ApplyAndClaimFanout(ctx context.Context, g queue.Guarded, claim finalization.Claim, before finalization.Conversation, notes *finalization.Notes, inputHash, outputHash string) (finalization.Fanout, error) {
	revision, ok := before.Comparison.(conversations.Revision)
	if !f.syncOnly || !ok {
		return finalization.Fanout{}, finalization.ErrInvalid
	}
	patch, err := f.finalizationPatch(before, notes, inputHash, outputHash)
	if err != nil {
		return finalization.Fanout{}, err
	}
	patch.InlineFanoutEpoch = claim.Epoch
	return f.commitFanout(ctx, g, claim, revision, patch, true, notes != nil && notes.Minimum != nil)
}

func (f finalizationDocuments) commitFanout(ctx context.Context, g queue.Guarded, claim finalization.Claim, revision conversations.Revision, patch conversations.Finalization, inline, minimum bool) (finalization.Fanout, error) {
	ref := conversations.Ref{Owner: claim.Intent.Ref.Owner, ID: claim.Intent.Ref.ID}
	fanout, err := f.jobs.ApplyAndClaimFanout(ctx, g, claim, inline, minimum, func(tx *docstore.Tx, row map[string]any) error {
		refused, stageErr := f.store.StageFinalization(tx, ref, revision, row, patch)
		if stageErr == nil && refused {
			return conversations.ErrLifecycleRefused
		}
		return stageErr
	})
	return fanout, finalizationWriteError(err)
}

func (f finalizationDocuments) finalizationPatch(before finalization.Conversation, notes *finalization.Notes, inputHash, outputHash string) (conversations.Finalization, error) {
	status := conversations.Completed
	patch := conversations.Finalization{Status: &status, SyncRelevance: before.Relevance, SyncFieldMask: f.syncOnly}
	if f.syncOnly {
		patch.SyncSourceProjection = before.SourceProjection
		scopes, err := conversations.RecordingSpeakerScopes(before.Transcript)
		if err != nil {
			return conversations.Finalization{}, finalization.ErrInvalid
		}
		patch.SyncSpeakerScopes = scopes
	}
	if before.Relevance != nil {
		patch.Discarded = new(false)
	}
	if notes != nil {
		if f.syncOnly {
			patch.SyncNotesWrittenAt = new(f.clock.Now().UTC())
			patch.SyncTerminalFamilyEnabled = before.StampTerminal
			patch.SyncTitleUpdate = notes.TitleUpdate
			patch.SyncOpenLoops = notes.OpenLoops
		}
		patch.Title, patch.Overview, patch.Sections = &notes.Title, &notes.Overview, &notes.Sections
		patch.ActionItems = notes.ActionItems
		if notes.Minimum != nil {
			patch.SyncMinimum = notes.Minimum
			patch.Discarded = &notes.Minimum.Discarded
		} else {
			patch.NotesInputHash, patch.NotesOutputHash = &inputHash, &outputHash
			patch.ServingSyncNotes = f.syncOnly
		}
	}
	return patch, nil
}

func finalizationWriteError(err error) error {
	switch {
	case errors.Is(err, conversations.ErrChanged):
		return finalization.ErrSourceChanged
	case errors.Is(err, docstore.ErrMissing), errors.Is(err, conversations.ErrRestricted), errors.Is(err, conversations.ErrLifecycleRefused):
		return finalization.ErrStale
	default:
		return err
	}
}
