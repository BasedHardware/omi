package finalizationdocs

import (
	"context"
	"errors"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type recordedRetraction map[string]int

func (p recordedRetraction) Retract(_ context.Context, a queue.Admitting, _ finalization.MergeJob, id string) error {
	p[id]++
	return a.Err()
}

func TestF36MergeCleanupRetainsSourcesAfterSurvivorLoss(t *testing.T) {
	t.Parallel()
	store, bench, a, claimed, base := cleanupFixture(t)
	retractions := recordedRetraction{}
	store.MergeRetraction = retractions
	if err := store.CleanupMergeSource(t.Context(), a, claimed, "a"); err != nil {
		t.Fatal(err)
	}
	if err := store.CleanupMergeSource(t.Context(), a, claimed, "a"); err != nil {
		t.Fatal(err)
	}
	if bench.Exists(t, base+"a") || retractions["a"] != 1 {
		t.Fatal("source replay spent retraction again")
	}
	if _, err := bench.Raw.Doc(base + claimed.Target).Delete(t.Context()); err != nil {
		t.Fatal(err)
	}
	err := store.CleanupMergeSource(t.Context(), a, claimed, "b")
	if !errors.Is(err, finalization.ErrStale) || !bench.Exists(t, base+"b") || retractions["b"] != 0 {
		t.Fatalf("missing survivor did not fence remaining source: %v", err)
	}
}

func TestF36MergeCleanupRequiresCurrentCorrectionsReceipt(t *testing.T) {
	t.Parallel()
	store, bench, a, claimed, base := cleanupFixture(t)
	retractions := recordedRetraction{}
	store.MergeRetraction = retractions
	row := read(t, bench, base+"b")
	row["transcript_corrections_moved_to"] = "somewhere-else"
	put(t, bench, base+"b", row)
	if err := store.CleanupMergeSource(t.Context(), a, claimed, "b"); !errors.Is(err, finalization.ErrStale) {
		t.Fatalf("wrong receipt authorized removal: %v", err)
	}
	if retractions["b"] != 0 || !bench.Exists(t, base+"b") {
		t.Fatal("source changed before receipt was valid")
	}
	row["transcript_corrections_moved_to"] = claimed.Target
	put(t, bench, base+"b", row)
	for _, id := range claimed.Sources {
		if err := store.CleanupMergeSource(t.Context(), a, claimed, id); err != nil {
			t.Fatal(err)
		}
	}
	if err := store.CompleteMergeCleanup(t.Context(), a, claimed); err != nil {
		t.Fatal(err)
	}
	if err := store.CompleteMergeCleanup(t.Context(), a, claimed); err != nil {
		t.Fatal(err)
	}
}

func cleanupFixture(t *testing.T) (Store, docstoretest.Bench, queue.Admitting, finalization.MergeJob, string) {
	t.Helper()
	store, bench, req := setup(t)
	owner := req.Ref.Owner
	base := "users/" + owner + "/conversations/"
	a := queue.AdmittingForTest(t, owner)
	for _, id := range []string{"a", "b"} {
		put(t, bench, base+id, document{"status": "completed"})
	}
	job, err := store.AdmitMerge(t.Context(), a, finalization.MergeRequest{Owner: owner, Sources: []string{"a", "b"}})
	if err != nil {
		t.Fatal(err)
	}
	claimed, err := store.ClaimMerge(t.Context(), a, owner, job.ID, 1)
	if err != nil {
		t.Fatal(err)
	}
	put(t, bench, base+job.Target, document{"status": "completed"})
	for _, id := range job.Sources {
		row := read(t, bench, base+id)
		row["transcript_corrections_moved_to"] = job.Target
		put(t, bench, base+id, row)
	}
	if err := store.RenewMerge(t.Context(), a, claimed, true); err != nil {
		t.Fatal(err)
	}
	return store, bench, a, claimed, base
}
