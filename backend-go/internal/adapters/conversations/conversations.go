// Package conversations reads stored conversations and applies finalization fields in Firestore.
package conversations

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"maps"
	"time"

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
	Title                           string
	Overview                        string
	Sections                        []string
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
	Title                           *string
	Overview                        *string
	Sections                        *[]string
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
	var revision Revision
	err = s.Docs.Fenced(ctx, g, ref.Owner, func(tx *docstore.Tx) error {
		parent, getErr := get(tx, ref, path)
		if getErr != nil {
			return getErr
		}
		current, revisionErr := rowRevision(ref, parent)
		if revisionErr != nil {
			return revisionErr
		}
		payload, payloadErr := readPayload(tx, ref, parent)
		if payloadErr != nil {
			return payloadErr
		}
		maps.Copy(parent, payload.values)
		row, revision = parent, current
		return nil
	})
	if err != nil {
		return Conversation{}, classify(err)
	}
	result, err := s.decode(ctx, g, ref, row, revision)
	if err != nil {
		return Conversation{}, classify(err)
	}
	if err := g.Err(); err != nil {
		return Conversation{}, err
	}
	return result, nil
}

// CheckLive rechecks the primary row and deletion intent before a gateway call.
func (s Store) CheckLive(ctx context.Context, g queue.Guarded, ref Ref, jobID string, revision int64) error {
	path, err := docstore.Doc("users", ref.Owner, "conversations", ref.ID)
	if err != nil {
		return classify(err)
	}
	return classify(s.Docs.Fenced(ctx, g, ref.Owner, func(tx *docstore.Tx) error {
		row, err := get(tx, ref, path)
		if err != nil {
			return err
		}
		status := Status(field[string](row, "status"))
		if (status != Processing && status != Completed) || field[bool](row, "discarded") ||
			field[string](row, "finalization_job_id") != jobID || field[int64](row, "finalization_revision") != revision {
			return docstore.ErrMissing
		}
		return nil
	}))
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
		current, revisionErr := rowRevision(ref, row)
		if revisionErr != nil {
			return revisionErr
		}
		if current != revision {
			return ErrChanged
		}
		if statusErr := validateStatus(patch); statusErr != nil {
			return statusErr
		}
		payload, payloadErr := readPayload(tx, ref, row)
		if payloadErr != nil {
			return payloadErr
		}
		maps.Copy(row, payload.values)
		fields, lifecycleRefused := finalizationFields(row, patch)
		refused = lifecycleRefused
		if len(fields) == 0 {
			return nil
		}
		write, repackErr := payload.repackNotes(fields)
		if repackErr != nil {
			return repackErr
		}
		return updateWithHome(tx, ref, path, fields, write)
	})
	if err == nil && refused {
		err = ErrLifecycleRefused
	}
	return classify(err)
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
	if !found || field[bool](row, "deleted") || field[bool](row, "is_deleted") {
		return nil, docstore.ErrMissing
	}
	if field[bool](row, "is_locked") || field[string](row, "data_protection_level") == "private" {
		return nil, ErrRestricted
	}
	return row, nil
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
	errPayloadWrite     = errors.New("conversations: finalization exceeds atomic payload budget")
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
	CausePayloadWrite  queue.Cause = "conversation_payload_write"
)

// Causes returns every cause emitted by this adapter.
func Causes() []queue.Cause {
	return []queue.Cause{CauseOwnerDeleting, CauseUnavailable, CauseRejected, CauseMissing,
		CauseChanged, CausePointer, CauseUnreadable, CauseRestricted, CausePayloadWrite}
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
	case errors.Is(err, errPayloadWrite):
		return queue.Classify(err, queue.Hold(CausePayloadWrite, time.Minute))
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
