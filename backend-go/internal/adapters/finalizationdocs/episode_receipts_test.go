package finalizationdocs

import (
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestF37RetainedActivitySurvivesNotesFailureAndReceiptsCommitOnce(t *testing.T) {
	t.Parallel()
	store, bench, req := setup(t)
	store.Codec = crypt.New("synthetic-episode-encryption-key-at-least-32-bytes")
	eid := "episode-a"
	episode := "users/" + req.Ref.Owner + "/episodes/" + eid
	receipt := "users/" + req.Ref.Owner + "/episode_segment_receipts/" + req.Ref.ID
	before, retained := store.Clock.Now().Add(-time.Hour), store.Clock.Now().Add(-time.Minute)
	put(t, bench, episode, document{"status": "live", "state_version": int64(4), "last_activity_at": before, "conversation_ids": []string{req.Ref.ID}})
	member, err := bench.Raw.Doc(conversationPath).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	speech := finalization.EpisodeSpeech{Member: req.Ref, EpisodeID: eid, MemberWritten: member.UpdateTime, At: retained, SegmentIDs: []string{"unplaced-a"}}
	a := queue.AdmittingForTest(t, req.Ref.Owner)
	if activityErr := store.RecordEpisodeSpeech(t.Context(), a, speech); activityErr != nil {
		t.Fatal(activityErr)
	}
	current := read(t, bench, episode)
	if current["state_version"] != int64(4) || !field[time.Time](current, "last_activity_at").Equal(retained) || bench.Exists(t, receipt) {
		t.Fatal("activity should be durable without consuming failed notes")
	}
	if closeErr := store.CloseEpisodeIdle(t.Context(), a, req.Ref.Owner, eid, before, 10*time.Minute); !errors.Is(closeErr, finalization.ErrStale) {
		t.Fatalf("stale idle close beat retained speech: %v", closeErr)
	}
	notes := finalization.EpisodeNotes{ExpectedVersion: 4, Content: json.RawMessage(`{"title":"Synthetic retained notes"}`)}
	for range 2 {
		if notesErr := store.CommitEpisodeNotes(t.Context(), a, speech, notes); notesErr != nil {
			t.Fatal(notesErr)
		}
	}
	current = read(t, bench, episode)
	content, err := store.Codec.Open(req.Ref.Owner, field[string](current, "content"))
	ids := field[[]any](read(t, bench, receipt), "ids")
	if err != nil || string(content) != string(notes.Content) || current["state_version"] != int64(5) || len(ids) != 1 {
		t.Fatalf("notes and receipt did not settle atomically: %v", err)
	}
}

func TestCommitEpisodeNotesFencesDeletionAfterPlanning(t *testing.T) {
	t.Parallel()
	for _, change := range []string{"account", "tombstone"} {
		t.Run(change, func(t *testing.T) {
			t.Parallel()
			store, bench, req := setup(t)
			store.Codec = crypt.New("synthetic-episode-encryption-key-at-least-32-bytes")
			base := "users/" + req.Ref.Owner
			episode := base + "/episodes/episode-a"
			receipt := base + "/episode_segment_receipts/" + req.Ref.ID
			put(t, bench, episode, document{"status": "closed", "state_version": int64(4), "conversation_ids": []string{req.Ref.ID}})
			member, err := bench.Raw.Doc(conversationPath).Get(t.Context())
			if err != nil {
				t.Fatal(err)
			}
			speech := finalization.EpisodeSpeech{
				Member: req.Ref, EpisodeID: "episode-a", MemberWritten: member.UpdateTime, SegmentIDs: []string{"unplaced-a"},
			}
			notes := finalization.EpisodeNotes{ExpectedVersion: 4, Content: json.RawMessage(`{"title":"Synthetic composed notes"}`)}
			want := finalization.ErrStale
			if change == "account" {
				want = docstore.ErrOwnerDeleting
				put(t, bench, "account_deletions/"+req.Ref.Owner, document{"wipe_status": "running"})
			} else {
				put(t, bench, base+"/deleted_conversations/"+req.Ref.ID, document{"conversation_id": req.Ref.ID})
			}
			a := queue.AdmittingForTest(t, req.Ref.Owner)
			if notesErr := store.CommitEpisodeNotes(t.Context(), a, speech, notes); !errors.Is(notesErr, want) {
				t.Fatalf("notes commit after %s deletion = %v, want %v", change, notesErr, want)
			}
			current := read(t, bench, episode)
			if current["state_version"] != int64(4) || current["content"] != nil || bench.Exists(t, receipt) {
				t.Fatalf("notes or receipt committed after %s deletion", change)
			}
		})
	}
}
