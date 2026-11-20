package finalizationdocs

import (
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestF22AbsorbReplayFencesOldEpochAndAppendsOnce(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	beginClaim(t, store, g, claim)
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
	plan := finalization.SmartAbsorbPlan{SurvivorID: "survivor", DonorWritten: donor.UpdateTime, SurvivorWritten: target.UpdateTime}
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
