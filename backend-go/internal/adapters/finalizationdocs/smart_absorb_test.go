package finalizationdocs

import (
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestF22AbsorbReplayFencesOldEpochAndAppendsOnce(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	beginClaim(t, store, g, claim)
	plan := seedAbsorbPair(t, store, bench, claim)
	targetPath := benchPath(finalization.Ref{Owner: claim.Intent.Ref.Owner, ID: plan.SurvivorID})
	result, err := store.Absorb(t.Context(), g, claim, plan)
	if err != nil || result.AlreadyApplied {
		t.Fatalf("absorb: %+v %v", result, err)
	}
	if refreshErr := store.ClaimRefresh(t.Context(), g, claim, result); refreshErr != nil {
		t.Fatal(refreshErr)
	}
	later := claim
	later.Epoch++
	beginClaim(t, store, g, later)
	if _, oldErr := store.Absorb(t.Context(), g, claim, plan); !errors.Is(oldErr, queue.ErrLease) {
		t.Fatalf("old claim resumed cleanup: %v", oldErr)
	}
	replay, err := store.Absorb(t.Context(), g, later, plan)
	if err != nil || !replay.AlreadyApplied {
		t.Fatalf("replay: %+v %v", replay, err)
	}
	if stale := store.CheckpointRefresh(t.Context(), g, claim, result); !errors.Is(stale, queue.ErrLease) {
		t.Fatalf("old refresh: %v", stale)
	}
	if refreshErr := store.ClaimRefresh(t.Context(), g, later, result); refreshErr != nil {
		t.Fatal(refreshErr)
	}
	if refreshErr := store.CheckpointRefresh(t.Context(), g, later, result); refreshErr != nil {
		t.Fatal(refreshErr)
	}
	speech := field[[]any](read(t, bench, targetPath), "transcript_segments")
	if len(speech) != 2 || read(t, bench, conversationPath)["sync_merged_into"] != "survivor" {
		t.Fatal("retry duplicated the fragment or discarded the redirect")
	}
}

func seedAbsorbPair(t *testing.T, store Store, bench docstoretest.Bench, claim finalization.Claim) finalization.SmartAbsorbPlan {
	t.Helper()
	now := store.Clock.Now()
	targetPath := benchPath(finalization.Ref{Owner: claim.Intent.Ref.Owner, ID: "survivor"})
	row := read(t, bench, conversationPath)
	row["status"], row["source"], row["data_protection_level"], row["client_device_id"] = "completed", "omi", "standard", "device"
	row["started_at"], row["finished_at"], row["created_at"] = now.Add(-90*time.Second), now, now.Add(-90*time.Second)
	row["transcript_segments"] = []document{{"text": "donor words", "start": 1.0, "end": 2.0}}
	put(t, bench, conversationPath, row)
	put(t, bench, targetPath, document{"status": "completed", "source": "omi", "data_protection_level": "standard", "client_device_id": "device",
		"started_at": now.Add(-180 * time.Second), "finished_at": now.Add(-90 * time.Second),
		"transcript_segments": []document{{"text": "survivor words", "start": 1.0, "end": 2.0}}})
	donor, err := bench.Raw.Doc(conversationPath).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	target, err := bench.Raw.Doc(targetPath).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	return finalization.SmartAbsorbPlan{SurvivorID: "survivor", DonorWritten: donor.UpdateTime, SurvivorWritten: target.UpdateTime}
}

func TestF22DeletedDonorCannotReplayOrRepointEpisode(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	beginClaim(t, store, g, claim)
	plan := seedAbsorbPair(t, store, bench, claim)
	donor := claim.Intent.Ref
	root := "users/" + donor.Owner + "/"
	store.Codec = crypt.New("synthetic-membership-encryption-key-at-least-32-bytes")
	content, err := store.Codec.Seal(donor.Owner, []byte(`{"moments":[{"conversation_id":"fixture-conversation"}]}`))
	if err != nil {
		t.Fatal(err)
	}
	put(t, bench, root+"episode_links/"+donor.ID, document{"episode_id": "covering"})
	put(t, bench, root+"episodes/covering", document{"conversation_ids": []string{donor.ID}, "state_version": int64(1), "content": content})
	put(t, bench, root+"episode_segment_receipts/"+donor.ID, document{"ids": []string{"speech"}})
	result, err := store.Absorb(t.Context(), g, claim, plan)
	if err != nil {
		t.Fatal(err)
	}
	putDeleteIntent(t, bench, donor)
	if _, err := store.Absorb(t.Context(), g, claim, plan); !errors.Is(err, finalization.ErrStale) {
		t.Fatalf("absorb replay accepted a deleted donor: %v", err)
	}
	if err := store.ClaimRefresh(t.Context(), g, claim, result); !errors.Is(err, finalization.ErrStale) {
		t.Fatalf("a deleted donor started refresh: %v", err)
	}
	if err := store.RepointEpisode(t.Context(), g, claim, result); !errors.Is(err, finalization.ErrStale) {
		t.Fatalf("a deleted donor repointed an episode: %v", err)
	}
	episode := read(t, bench, root+"episodes/covering")
	ids := field[[]any](episode, "conversation_ids")
	if len(ids) != 1 || ids[0] != donor.ID || episode["state_version"] != int64(1) || episode["content"] != content ||
		bench.Exists(t, root+"episode_links/"+result.Survivor.ID) ||
		bench.Exists(t, root+"episode_segment_receipts/"+result.Survivor.ID) {
		t.Fatal("deleted donor moved an episode moment, membership, or receipt")
	}
}
