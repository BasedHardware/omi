package conversations_test

import (
	"errors"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

func TestF32TombstoneRefusesLoadAndNotesOrHomeWrites(t *testing.T) {
	t.Parallel()
	b, s, g := open(t)
	ref := seed(t, b, "delete-intent", map[string]any{"status": "processing"})
	before, err := s.Load(t.Context(), g, ref)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := b.Raw.Doc("users/"+ref.Owner+"/deleted_conversations/"+ref.ID).Set(t.Context(), map[string]any{"conversation_id": ref.ID}); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Load(t.Context(), g, ref); !errors.Is(err, docstore.ErrMissing) {
		t.Fatalf("tombstoned row was readable: %v", err)
	}
	patch := conversations.Finalization{Status: new(conversations.Completed), Overview: new("must not persist")}
	if err := s.ApplyFinalization(t.Context(), g, before.Revision, patch); !errors.Is(err, docstore.ErrMissing) {
		t.Fatalf("tombstoned row accepted a patch: %v", err)
	}
	if row := read(t, b, ref); row["status"] != "processing" || row["structured"] != nil ||
		b.Exists(t, "users/"+ref.Owner+"/episode_links/"+ref.ID) || b.Exists(t, "users/"+ref.Owner+"/episode_links/home_feed_control") {
		t.Fatal("notes or Home receipts changed while deletion was pending")
	}
}

func TestSyncNotesRecoveryKeepsBindingAndPaidCallKeepsDeletionFence(t *testing.T) {
	t.Parallel()
	for _, marker := range []struct {
		name, path string
		data       map[string]any
		want       error
	}{
		{"account", "account_deletions/" + owner, map[string]any{"wipe_status": "pending"}, docstore.ErrOwnerDeleting},
		{"conversation", "users/" + owner + "/deleted_conversations/recovery", map[string]any{"conversation_id": "recovery"}, docstore.ErrMissing},
	} {
		t.Run(marker.name, func(t *testing.T) {
			t.Parallel()
			b, s, g := open(t)
			ref := seed(t, b, "recovery", map[string]any{
				"status": "processing", "finalization_engine": "go", "finalization_job_id": "current",
				"finalization_revision": int64(1), "sync_content_revision": int64(2),
			})
			if _, err := b.Raw.Doc(marker.path).Set(t.Context(), marker.data); err != nil {
				t.Fatal(err)
			}
			if err := s.CheckSyncNotesRecoverySource(t.Context(), g, ref, "current", 1); err != nil {
				t.Fatalf("read-only receipt lookup source check: %v", err)
			}
			if err := s.CheckSyncNotesRecoverySource(t.Context(), g, ref, "stale", 1); !errors.Is(err, docstore.ErrMissing) {
				t.Fatalf("stale recovery binding: %v", err)
			}
			if err := s.CheckLive(t.Context(), g, ref, "current", 1, 2); !errors.Is(err, marker.want) {
				t.Fatalf("paid call deletion fence: got %v, want %v", err, marker.want)
			}
		})
	}
}
