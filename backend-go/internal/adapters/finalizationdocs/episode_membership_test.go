package finalizationdocs

import (
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestF26IntakeThenAbsorbRepointsMembershipAndReceiptsOnce(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	beginClaim(t, store, g, claim)
	store.Codec = crypt.New("synthetic-membership-encryption-key-at-least-32-bytes")
	now := store.Clock.Now()
	donor := claim.Intent.Ref
	survivor := finalization.Ref{Owner: donor.Owner, ID: "survivor"}
	root := "users/" + donor.Owner + "/"
	episode := root + "episodes/covering"
	content, err := store.Codec.Seal(donor.Owner, []byte(`{"moments":[{"conversation_id":"fixture-conversation"}]}`))
	if err != nil {
		t.Fatal(err)
	}
	put(t, bench, episode, document{"status": "live", "state_version": int64(1),
		"started_at": now.Add(-180 * time.Second), "last_activity_at": now.Add(-1 * time.Minute), "content": content})
	put(t, bench, root+"episode_links/current", document{"episode_id": "covering"})
	row := read(t, bench, conversationPath)
	row["status"], row["started_at"], row["finished_at"] = "completed", now.Add(-90*time.Second), now
	put(t, bench, conversationPath, row)
	uploaded, err := bench.Raw.Doc(conversationPath).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	a := queue.AdmittingForTest(t, donor.Owner)
	for range 2 {
		id, intakeErr := store.AttachEpisodeIntake(t.Context(), a, donor, uploaded.UpdateTime, true)
		if intakeErr != nil || id != "covering" {
			t.Fatalf("intake: %q %v", id, intakeErr)
		}
	}
	if state := read(t, bench, episode); state["state_version"] != int64(2) {
		t.Fatal("intake replay spent another membership revision")
	}
	row = read(t, bench, conversationPath)
	row["deleted"], row["sync_merged_into"] = true, survivor.ID
	put(t, bench, conversationPath, row)
	put(t, bench, benchPath(survivor), document{"status": "completed", "sync_content_revision": int64(2), "smart_merge": document{"revision": int64(1)}})
	for _, ns := range []string{"", "content-v1:"} {
		put(t, bench, root+"episode_segment_receipts/"+ns+donor.ID, document{"ids": []string{ns + "speech"}})
	}
	result := finalization.SmartAbsorbResult{Survivor: survivor, Revision: 1, SyncRevision: 2}
	stale := claim
	stale.Epoch++
	if staleErr := store.RepointEpisode(t.Context(), g, stale, result); !errors.Is(staleErr, queue.ErrLease) {
		t.Fatalf("foreign epoch repointed episode: %v", staleErr)
	}
	for range 2 {
		if repointErr := store.RepointEpisode(t.Context(), g, claim, result); repointErr != nil {
			t.Fatal(repointErr)
		}
	}
	updated := read(t, bench, episode)
	ids := field[[]any](updated, "conversation_ids")
	if len(ids) != 1 || ids[0] != survivor.ID || updated["state_version"] != int64(3) ||
		read(t, bench, benchPath(survivor))["episode_id"] != "covering" ||
		read(t, bench, root+"episode_links/"+survivor.ID)["episode_id"] != "covering" {
		t.Fatal("membership and reverse link did not repoint exactly once")
	}
	verified, err := store.Codec.Open(donor.Owner, field[string](updated, "content"))
	var notes struct {
		Moments []struct {
			ID string `json:"conversation_id"`
		} `json:"moments"`
	}
	if err != nil || json.Unmarshal(verified, &notes) != nil || len(notes.Moments) != 1 || notes.Moments[0].ID != survivor.ID {
		t.Fatal("encrypted moment was not repointed")
	}
	for _, ns := range []string{"", "content-v1:"} {
		ids := field[[]any](read(t, bench, root+"episode_segment_receipts/"+ns+survivor.ID), "ids")
		if len(ids) != 1 || ids[0] != ns+"speech" {
			t.Fatal("receipt namespaces did not move exactly once")
		}
	}
}
