package conversations_test

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/objectlake"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type transcriptReadFunc func(context.Context, docstore.Live, string, string, map[string]any) ([]json.RawMessage, error)

func (read transcriptReadFunc) Read(ctx context.Context, live docstore.Live, owner, id string, pointer map[string]any) ([]json.RawMessage, error) {
	return read(ctx, live, owner, id, pointer)
}

func TestOffloadedTranscriptKeepsTheOriginalWriteFence(t *testing.T) {
	t.Parallel()
	b, store, guard := open(t)
	ref := seed(t, b, "offloaded", map[string]any{
		"status": "processing", "visibility": "shared", "transcript_segments": map[string]any{"key": "first"},
	})
	store.Offload = transcriptReadFunc(func(ctx context.Context, live docstore.Live, owner, id string, pointer map[string]any) ([]json.RawMessage, error) {
		if live.Err() != nil || live.Tenant() != ref.Owner || owner != ref.Owner || id != ref.ID || pointer["key"] != "first" {
			t.Error("invalid transcript reader authority")
		}
		// A concurrent transaction can advance the row once Load releases its read transaction.
		path := b.Raw.Doc("users/" + owner + "/conversations/" + id)
		_, err := path.Set(ctx, map[string]any{"status": "processing", "transcript_segments": []any{}})
		return []json.RawMessage{json.RawMessage(`{"text":"synthetic offloaded speech"}`)}, err
	})
	snapshot, err := store.Load(t.Context(), guard, ref)
	if err != nil || len(snapshot.Transcript) != 1 {
		t.Fatalf("offloaded load: %+v %v", snapshot, err)
	}
	status := conversations.Completed
	err = store.ApplyFinalization(t.Context(), guard, snapshot.Revision, conversations.Finalization{Status: &status})
	assertOutcome(t, err, conversations.ErrChanged, queue.Retry(conversations.CauseChanged, 0))
}

func TestOffloadedStorageOutagesAreRetryable(t *testing.T) {
	t.Parallel()
	b, store, guard := open(t)
	ref := seed(t, b, "offloaded", map[string]any{"status": "processing", "transcript_segments": map[string]any{"key": "first"}})
	store.Offload = transcriptReadFunc(func(context.Context, docstore.Live, string, string, map[string]any) ([]json.RawMessage, error) {
		return nil, objectlake.ErrUnavailable
	})
	_, err := store.Load(t.Context(), guard, ref)
	assertOutcome(t, err, objectlake.ErrUnavailable, queue.Retry(conversations.CauseUnavailable, 0))
}
