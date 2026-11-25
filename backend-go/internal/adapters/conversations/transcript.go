package conversations

import (
	"context"
	"encoding/json"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func (s Store) decode(ctx context.Context, g queue.Guarded, ref Ref, row map[string]any, revision Revision) (Conversation, error) {
	transcript, err := s.snapshotTranscript(ctx, g, ref, row)
	if err != nil {
		return Conversation{}, err
	}
	structured := field[map[string]any](row, "structured")
	sections, integrity := readNotesSections(structured["sections"])
	outputHash := ""
	if integrity {
		outputHash = field[string](row, notesOutputHashField)
	}
	return Conversation{
		Revision:             revision,
		Status:               Status(field[string](row, "status")),
		FinalizationStatus:   FinalizationStatus(field[string](row, "finalization_status")),
		FinalizationJobID:    field[string](row, "finalization_job_id"),
		FinalizationRevision: field[int64](row, "finalization_revision"),
		SyncContentRevision:  field[int64](row, "sync_content_revision"),
		ProtectionLevel:      field[string](row, "data_protection_level"),
		Discarded:            field[bool](row, "discarded"),
		Title:                effectiveTitle(row, field[string](structured, "title")),
		Overview:             effectiveOverview(row, field[string](structured, "overview")),
		Sections:             sections, NotesInputHash: field[string](row, notesInputHashField), NotesOutputHash: outputHash,
		CreatedAt:            field[time.Time](row, "created_at"),
		StartedAt:            field[time.Time](row, "started_at"),
		FinishedAt:           field[time.Time](row, "finished_at"),
		SummaryCoversThrough: field[time.Time](row, "summary_covers_through"),
		Transcript:           transcript,
	}, nil
}

func (s Store) snapshotTranscript(ctx context.Context, g queue.Guarded, ref Ref, row map[string]any) ([]json.RawMessage, error) {
	raw := row["transcript_segments"]
	if pointer, ok := raw.(map[string]any); ok && s.Offload != nil {
		return s.Offload.Read(ctx, g, ref.Owner, ref.ID, pointer)
	}
	return s.transcript(ref.Owner, raw, field[bool](row, "transcript_segments_compressed"))
}

func (s Store) transcript(owner string, value any, compressed bool) ([]json.RawMessage, error) {
	switch raw := value.(type) {
	case nil:
		// Python's v3 reader defaults a missing or null field to an empty list.
		return []json.RawMessage{}, nil
	case []any:
		// Lists predate the compression flag. Python accepts them even with a stale flag.
		compressed = false
	case []byte:
		if !compressed {
			return nil, crypt.ErrUnreadable
		}
		value = map[string][]byte{"base64": raw}
	case string:
		// The codec authenticates before interpreting encrypted JSON or encrypted zlib hex.
	case map[string]any:
		return nil, ErrPointer
	default:
		return nil, crypt.ErrUnreadable
	}
	wire, err := json.Marshal(value)
	if err != nil {
		return nil, crypt.ErrUnreadable
	}
	segments, err := s.Codec.Decode(owner, crypt.Transcript{Segments: wire, Compressed: compressed})
	if err != nil {
		return nil, err
	}
	return stripIdentitySidecars(segments)
}

func stripIdentitySidecars(segments []json.RawMessage) ([]json.RawMessage, error) {
	for i, segment := range segments {
		var fields map[string]json.RawMessage
		if err := json.Unmarshal(segment, &fields); err != nil {
			return nil, crypt.ErrUnreadable
		}
		// These storage sidecars require separate authority or Python's internal hydration.
		for _, name := range []string{"recurring_voice_id", "speaker_grouping_internal", "provider_speaker",
			"speaker_grouping_shadow", "speaker_grouping_shadow_expires_at"} {
			delete(fields, name)
		}
		plain, err := json.Marshal(fields)
		if err != nil {
			return nil, crypt.ErrUnreadable
		}
		segments[i] = plain
	}
	return segments, nil
}
