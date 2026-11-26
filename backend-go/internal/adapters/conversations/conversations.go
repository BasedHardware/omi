// Package conversations reads stored conversations and applies finalization fields in Firestore.
package conversations

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/objectlake"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Ref identifies a conversation in its owner's collection.
type Ref struct {
	Owner string
	ID    string
}

// Revision is an opaque, document-bound comparison token from Load.
type Revision struct {
	ref    Ref
	digest [sha256.Size]byte
}

// Status is the conversation lifecycle status stored by Python.
type Status string

// The lifecycle statuses from models/conversation_enums.py.
const (
	InProgress Status = "in_progress"
	Processing Status = "processing"
	Merging    Status = "merging"
	Completed  Status = "completed"
	Failed     Status = "failed"
)

// FinalizationStatus is the status of the finalization job mirrored on the conversation.
type FinalizationStatus string

// The finalization states mirrored by conversation_finalization_jobs.py.
const (
	Queued      FinalizationStatus = "queued"
	Leased      FinalizationStatus = "leased"
	BlockedBYOK FinalizationStatus = "blocked_byok"
	Finalized   FinalizationStatus = "completed"
	DeadLetter  FinalizationStatus = "dead_letter"
)

// Conversation is the stored conversation view for finalization.
type Conversation struct {
	Revision                        Revision
	Status                          Status
	FinalizationStatus              FinalizationStatus
	FinalizationJobID               string
	FinalizationRevision            int64
	SyncContentRevision             int64
	ProtectionLevel                 string
	Discarded                       bool
	RecordingLayer                  bool
	NoDerivedEffects                bool
	UntrustedCapture                bool
	PendingMinimum                  bool
	SyncMinimumApplied              bool
	BatchOwned, HasAudio, HasPhotos bool
	AppPlatform                     string
	Title                           string
	Overview                        string
	Sections                        []finalization.NoteSection
	NotesInputHash, NotesOutputHash string
	CreatedAt                       time.Time
	StartedAt                       time.Time
	FinishedAt                      time.Time
	SummaryCoversThrough            time.Time
	Transcript                      []json.RawMessage
}

// Finalization is a partial update. Nil fields leave the corresponding Firestore fields alone.
type Finalization struct {
	Status                          *Status
	FinalizationStatus              *FinalizationStatus
	Discarded                       *bool
	SyncMinimum                     *finalization.NotesMinimum
	ServingSyncNotes                bool
	SyncFieldMask                   bool
	SyncSourceProjection            *finalization.SyncSourceProjection
	SyncSpeakerScopes               []string
	SyncNotesWrittenAt              *time.Time
	SyncTerminalFamilyEnabled       bool
	SyncRelevance                   *finalization.RelevanceDecision
	SyncTitleUpdate                 *finalization.SyncTitleUpdate
	SyncOpenLoops                   *finalization.SyncOpenLoops
	EmptyDiscardFanoutEpoch         int64
	InlineFanoutEpoch               int64
	Title                           *string
	Overview                        *string
	Sections                        *[]finalization.NoteSection
	ActionItems                     *[]map[string]any
	NotesInputHash, NotesOutputHash *string
	FinishedAt                      *time.Time
	SummaryCoversThrough            *time.Time
}

// TranscriptReader resolves a transcript pointer under the original read guard.
type TranscriptReader interface {
	Read(ctx context.Context, live docstore.Live, owner, conversation string, pointer map[string]any) ([]json.RawMessage, error)
}

// Store implements guarded Load and ApplyFinalization ports. A consumer defines the
// interface alongside its other ports.
type Store struct {
	Docs    *docstore.Store
	Codec   crypt.Codec
	Offload TranscriptReader
}

// Load reads an existing, readable conversation for the guarded owner.
func (s Store) Load(ctx context.Context, g queue.Guarded, ref Ref) (Conversation, error) {
	path, err := docstore.Doc("users", ref.Owner, "conversations", ref.ID)
	if err != nil {
		return Conversation{}, classify(err)
	}
	var row map[string]any
	err = s.Docs.Fenced(ctx, g, ref.Owner, func(tx *docstore.Tx) error {
		var getErr error
		row, getErr = get(tx, ref, path)
		return getErr
	})
	if err != nil {
		return Conversation{}, classify(err)
	}
	return s.DecodeFencedSnapshot(ctx, g, ref, row)
}

// DecodeFencedSnapshot hydrates a source already read with the owner and
// tombstone fences inside the caller's transaction.
func (s Store) DecodeFencedSnapshot(ctx context.Context, g queue.Guarded, ref Ref, row map[string]any) (Conversation, error) {
	if g.Tenant() != ref.Owner {
		return Conversation{}, classify(docstore.ErrOwnerMismatch)
	}
	if err := g.Err(); err != nil {
		return Conversation{}, err
	}
	result, err := s.decode(ctx, g, ref, row)
	if err != nil {
		return Conversation{}, classify(err)
	}
	if err := g.Err(); err != nil {
		return Conversation{}, err
	}
	return result, nil
}

// CheckLive rechecks the primary row and deletion intent before a gateway call.
func (s Store) CheckLive(ctx context.Context, g queue.Guarded, ref Ref, jobID string, revision, syncRevision int64) error {
	path, err := docstore.Doc("users", ref.Owner, "conversations", ref.ID)
	if err != nil {
		return classify(err)
	}
	return classify(s.Docs.Fenced(ctx, g, ref.Owner, func(tx *docstore.Tx) error {
		row, err := get(tx, ref, path)
		if err != nil {
			return err
		}
		return checkNotesSource(row, jobID, revision, syncRevision, syncRevision > 0)
	}))
}

// CheckSyncNotesRecoverySource checks the binding for a gateway receipt GET.
// A subsequent paid call or write independently checks deletion authority.
func (s Store) CheckSyncNotesRecoverySource(ctx context.Context, g queue.Guarded, ref Ref, jobID string, revision int64) error {
	var row map[string]any
	found, err := s.Docs.ReadGuarded(ctx, g, ref.Owner, "conversations", ref.ID, &row)
	if err != nil {
		return classify(err)
	}
	if err := readable(found, row); err != nil {
		return classify(err)
	}
	// Recovery may fetch an earlier operation to reconcile a revision change.
	return classify(checkNotesSource(row, jobID, revision, 0, true))
}

func checkNotesSource(row map[string]any, jobID string, revision, syncRevision int64, requireGo bool) error {
	status := Status(field[string](row, "status"))
	if (status != Processing && status != Completed) || field[bool](row, "discarded") ||
		field[string](row, "finalization_job_id") != jobID || field[int64](row, "finalization_revision") != revision ||
		requireGo && field[string](row, "finalization_engine") != "go" {
		return docstore.ErrMissing
	}
	if syncRevision > 0 && field[int64](row, "sync_content_revision") != syncRevision {
		return ErrChanged
	}
	return nil
}

// ApplyFinalization updates the existing conversation if its stored contents still match
// the revision read before processing. A changed revision requires a fresh load and decision.
// ErrLifecycleRefused reports that a terminal transition was refused, after any content
// fields and their Home receipts have committed.
func (s Store) ApplyFinalization(ctx context.Context, g queue.Guarded, revision Revision, patch Finalization) error {
	ref := revision.ref
	path, err := docstore.Doc("users", ref.Owner, "conversations", ref.ID)
	if err != nil {
		return classify(err)
	}
	var refused bool
	err = s.Docs.Fenced(ctx, g, ref.Owner, func(tx *docstore.Tx) error {
		row, getErr := get(tx, ref, path)
		if getErr != nil {
			return getErr
		}
		var stageErr error
		refused, stageErr = s.StageFinalization(tx, ref, revision, row, patch)
		return stageErr
	})
	if err == nil && refused {
		err = ErrLifecycleRefused
	}
	return classify(err)
}

// StageFinalization applies the revision-checked update inside an already
// fenced transaction, letting a caller commit dependent job state atomically.
func (s Store) StageFinalization(tx *docstore.Tx, ref Ref, revision Revision, row map[string]any, patch Finalization) (bool, error) {
	if ref != revision.ref {
		return false, ErrChanged
	}
	path, err := docstore.Doc("users", ref.Owner, "conversations", ref.ID)
	if err != nil {
		return false, err
	}
	current, revisionErr := rowRevision(ref, row)
	if revisionErr != nil {
		return false, revisionErr
	}
	if current != revision {
		return false, ErrChanged
	}
	if statusErr := validateStatus(patch); statusErr != nil {
		return false, statusErr
	}
	fields, lifecycleRefused := finalizationFields(row, patch)
	if patch.SyncFieldMask && !lifecycleRefused {
		if maskErr := s.stageSyncFields(ref.Owner, fields, row, patch); maskErr != nil {
			return false, maskErr
		}
		// The notes replace the structured content for the checked sync
		// revision even when the existing corrections blob is reused.
		if patch.Sections != nil {
			fields["home_content_invalidated"] = false
		}
	}
	if len(fields) == 0 {
		return lifecycleRefused, nil
	}
	return lifecycleRefused, updateWithHome(tx, ref, path, fields, patch.SyncFieldMask && !lifecycleRefused)
}

func get(tx *docstore.Tx, ref Ref, path docstore.Ref) (map[string]any, error) {
	tombstone, err := docstore.Doc("users", ref.Owner, "deleted_conversations", ref.ID)
	if err != nil {
		return nil, err
	}
	var marker map[string]any
	deleted, err := tx.Get(tombstone, &marker)
	if err != nil {
		return nil, err
	}
	if deleted {
		return nil, docstore.ErrMissing
	}
	var row map[string]any
	found, err := tx.Get(path, &row)
	if err != nil {
		return nil, err
	}
	return row, readable(found, row)
}

func readable(found bool, row map[string]any) error {
	if !found || field[bool](row, "deleted") || field[bool](row, "is_deleted") {
		return docstore.ErrMissing
	}
	if field[bool](row, "is_locked") || field[string](row, "data_protection_level") == "private" {
		return ErrRestricted
	}
	return nil
}

func field[T any](row map[string]any, name string) T {
	value, ok := row[name].(T)
	if !ok {
		var zero T
		return zero
	}
	return value
}

// Errors callers can match without inspecting Firestore messages or conversation data.
var (
	ErrChanged     = errors.New("conversations: source changed")
	ErrPointer     = errors.New("conversations: object-lake transcript requires a reader")
	ErrRestricted  = errors.New("conversations: protected row does not permit finalization")
	ErrUndecodable = errors.New("conversations: unsupported document encoding")
	// ErrLifecycleRefused reports a refused lifecycle transition after any content commit.
	ErrLifecycleRefused = errors.New("conversations: terminal lifecycle transition refused")
	ErrStatus           = errors.New("conversations: invalid lifecycle update")
)

// Causes returned by the adapter. Consumers register Causes with their kind.
const (
	CauseOwnerDeleting queue.Cause = "conversation_owner_deleting"
	CauseUnavailable   queue.Cause = "conversation_store_unavailable"
	CauseRejected      queue.Cause = "conversation_store_rejected"
	CauseMissing       queue.Cause = "conversation_missing"
	CauseChanged       queue.Cause = "conversation_source_changed"
	CausePointer       queue.Cause = "conversation_transcript_pointer"
	CauseUnreadable    queue.Cause = "conversation_unreadable"
	CauseRestricted    queue.Cause = "conversation_restricted"
)

// Causes returns every cause emitted by this adapter.
func Causes() []queue.Cause {
	return []queue.Cause{CauseOwnerDeleting, CauseUnavailable, CauseRejected, CauseMissing,
		CauseChanged, CausePointer, CauseUnreadable, CauseRestricted}
}

func classify(err error) error {
	var fault *docstore.CallError
	switch {
	case err == nil, errors.Is(err, queue.ErrLease), errors.Is(err, context.Canceled):
		return err
	case errors.Is(err, docstore.ErrOwnerDeleting):
		return queue.Classify(err, queue.Hold(CauseOwnerDeleting, time.Minute))
	case errors.Is(err, docstore.ErrMissing):
		return queue.Classify(err, queue.Fail(CauseMissing))
	case errors.Is(err, ErrChanged), errors.Is(err, objectlake.ErrChanged):
		return queue.Classify(err, queue.Retry(CauseChanged, 0))
	case errors.Is(err, ErrPointer):
		return queue.Classify(err, queue.Fail(CausePointer))
	case errors.Is(err, ErrRestricted), errors.Is(err, objectlake.ErrRestricted):
		return queue.Classify(err, queue.Fail(CauseRestricted))
	case errors.Is(err, crypt.ErrUnreadable), errors.Is(err, ErrUndecodable), errors.Is(err, objectlake.ErrCorrupt),
		errors.Is(err, objectlake.ErrAbsent), errors.Is(err, objectlake.ErrShredded):
		return queue.Classify(err, queue.Fail(CauseUnreadable))
	case errors.Is(err, docstore.ErrExists), errors.Is(err, context.DeadlineExceeded), errors.Is(err, objectlake.ErrUnavailable),
		errors.As(err, &fault) && fault.Kind == docstore.KindTransient:
		return queue.Classify(err, queue.Retry(CauseUnavailable, 0))
	default:
		return queue.Classify(err, queue.Fail(CauseRejected))
	}
}
