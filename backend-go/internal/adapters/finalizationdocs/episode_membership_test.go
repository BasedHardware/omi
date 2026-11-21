package finalizationdocs

import (
	"encoding/json"
	"errors"
	"slices"
	"testing"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
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
	h := queuetest.Open(t, queuetest.Policy(), finalization.Declaration(Causes()...))
	service := finalization.Service{Queue: h.Store, EpisodeIntake: store}
	for range 2 {
		id, intakeErr := service.AttachEpisodeIntake(t.Context(), donor, uploaded.UpdateTime, true)
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
	// A partially migrated reverse link can be repaired without consuming receipts again.
	partial := read(t, bench, benchPath(survivor))
	delete(partial, "episode_id")
	put(t, bench, benchPath(survivor), partial)
	if repointErr := store.RepointEpisode(t.Context(), g, claim, result); repointErr != nil {
		t.Fatal(repointErr)
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

func TestRepairEpisodeIntakeRequiresCurrentReceiptAndExistingMembership(t *testing.T) {
	t.Parallel()
	store, bench, req := setup(t)
	ref := req.Ref
	root := "users/" + ref.Owner + "/"
	episodePath := root + "episodes/covering"
	linkPath := root + "episode_links/" + ref.ID
	now := store.Clock.Now()
	put(t, bench, episodePath, document{"status": "live", "state_version": int64(7),
		"started_at": now.Add(-time.Minute), "conversation_ids": []string{ref.ID}})
	put(t, bench, root+"episode_links/current", document{"episode_id": "covering"})
	row := document{"status": "completed", "started_at": now, "finished_at": now}
	snapshotTime := func(path string) time.Time {
		t.Helper()
		snapshot, err := bench.Raw.Doc(path).Get(t.Context())
		if err != nil {
			t.Fatal(err)
		}
		return snapshot.UpdateTime
	}

	h := queuetest.Open(t, queuetest.Policy(), finalization.Declaration(Causes()...))
	service := finalization.Service{Queue: h.Store, EpisodeIntake: store}
	put(t, bench, conversationPath, row)
	unbound := snapshotTime(conversationPath)
	episodeVersion := snapshotTime(episodePath)
	if id, err := service.RepairEpisodeIntake(t.Context(), ref, unbound); err != nil || id != "" {
		t.Fatalf("unbound intake must do nothing: %q %v", id, err)
	}
	if !snapshotTime(conversationPath).Equal(unbound) || !snapshotTime(episodePath).Equal(episodeVersion) {
		t.Fatal("unbound intake modified conversation or covering episode")
	}
	// Python selected the episode, but the reverse link is missing.
	row["episode_id"] = "covering"
	put(t, bench, conversationPath, row)
	receipt := snapshotTime(conversationPath)
	if _, err := service.RepairEpisodeIntake(t.Context(), ref, receipt.Add(-time.Second)); !errors.Is(err, finalization.ErrStale) {
		t.Fatalf("stale repair receipt: %v", err)
	}
	if !snapshotTime(conversationPath).Equal(receipt) {
		t.Fatal("stale repair changed the conversation")
	}
	if _, err := bench.Raw.Doc(linkPath).Get(t.Context()); status.Code(err) != codes.NotFound {
		t.Fatalf("stale repair changed the link: %v", err)
	}
	if id, err := service.RepairEpisodeIntake(t.Context(), ref, receipt); err != nil || id != "covering" {
		t.Fatalf("valid repair: %q %v", id, err)
	}
	if bound := read(t, bench, linkPath); bound["episode_id"] != "covering" ||
		!slices.Contains(field[[]any](bound, "episode_ids"), any("covering")) {
		t.Fatalf("valid repair did not bind episode: %v", bound)
	}
	if read(t, bench, conversationPath)["episode_id"] != "covering" {
		t.Fatal("valid repair did not bind conversation")
	}
	boundConversation, boundLink := snapshotTime(conversationPath), snapshotTime(linkPath)
	if id, err := service.RepairEpisodeIntake(t.Context(), ref, receipt); err != nil || id != "covering" {
		t.Fatalf("bound replay: %q %v", id, err)
	}
	if !snapshotTime(conversationPath).Equal(boundConversation) || !snapshotTime(linkPath).Equal(boundLink) ||
		!snapshotTime(episodePath).Equal(episodeVersion) {
		t.Fatal("bound replay modified conversation, link or episode")
	}
}
