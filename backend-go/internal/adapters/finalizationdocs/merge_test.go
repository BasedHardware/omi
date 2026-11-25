package finalizationdocs

import (
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestF23MergeAdmissionIsAllOrNothingAndSealRechecksOwnership(t *testing.T) {
	t.Parallel()
	store, bench, req := setup(t)
	owner := req.Ref.Owner
	base := "users/" + owner + "/conversations/"
	a := queue.AdmittingForTest(t, owner)
	for _, id := range []string{"a", "b", "c"} {
		put(t, bench, base+id, document{"status": "completed"})
	}
	type result struct {
		job finalization.MergeJob
		err error
	}
	results := make(chan result, 2)
	for _, sources := range [][]string{{"a", "b"}, {"b", "c"}} {
		go func() {
			job, err := store.AdmitMerge(t.Context(), a, finalization.MergeRequest{Owner: owner, Sources: sources})
			results <- result{job, err}
		}()
	}
	first, second := <-results, <-results
	if first.err != nil {
		first, second = second, first
	}
	if first.err != nil || first.job.Target == "" || !errors.Is(second.err, finalization.ErrStale) {
		t.Fatalf("merge outcomes: %+v %+v", first, second)
	}
	for _, id := range first.job.Sources {
		if read(t, bench, base+id)["merge_job_id"] != first.job.ID {
			t.Fatalf("lost source %s", id)
		}
	}
	if _, err := store.ClaimMerge(t.Context(), a, owner, first.job.ID, 2); !errors.Is(err, finalization.ErrStale) {
		t.Fatalf("wrong generation: %v", err)
	}
	claim, err := store.ClaimMerge(t.Context(), a, owner, first.job.ID, 1)
	if err != nil || claim.Epoch != 1 || len(claim.Sources) != 2 || !claim.LeaseUntil.Equal(store.Clock.Now().Add(10*time.Minute)) {
		t.Fatalf("claim: %+v %v", claim, err)
	}
	bound := read(t, bench, base+"b")
	bound["is_locked"] = true
	put(t, bench, base+"b", bound)
	store.Clock = clock.Fixed{T: store.Clock.Now().Add(30 * time.Second)}
	if err := store.RenewMerge(t.Context(), a, claim, true); !errors.Is(err, finalization.ErrStale) {
		t.Fatalf("sealed a locked source: %v", err)
	}
	if read(t, bench, jobs+"/"+claim.ID)["phase"] != string(rules.MergePreparing) {
		t.Fatal("failed phase transition committed")
	}
}

func TestF24AndF36RollbackWaitsForTargetRetractionAndSealedRetryKeepsTarget(t *testing.T) {
	t.Parallel()
	for _, sealed := range []bool{false, true} {
		name := "preparing"
		if sealed {
			name = "sealed"
		}
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			testMergeRecovery(t, sealed)
		})
	}
}

func testMergeRecovery(t *testing.T, sealed bool) {
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
	claim, err := store.ClaimMerge(t.Context(), a, owner, job.ID, 1)
	if err != nil {
		t.Fatal(err)
	}
	if sealed {
		if sealErr := store.RenewMerge(t.Context(), a, claim, true); sealErr != nil {
			t.Fatal(sealErr)
		}
	}
	put(t, bench, base+job.Target, document{"status": "processing"})
	store.Clock = clock.Fixed{T: claim.LeaseUntil}
	recovery, err := store.BeginMergeRecovery(t.Context(), a, owner, job.ID)
	if err != nil || recovery.Job.Target != job.Target || recovery.Job.Epoch != claim.Epoch+1 {
		t.Fatalf("recovery: %+v %v", recovery, err)
	}
	if sealed {
		if recovery.Action != rules.MergeResumeCleanup || recovery.Job.Generation != 2 ||
			read(t, bench, base+"a")["merge_job_id"] != job.ID {
			t.Fatalf("sealed recovery released a source or lost target: %+v", recovery)
		}
		return
	}
	if recovery.Action != rules.MergeRollback {
		t.Fatalf("unsealed recovery: %+v", recovery)
	}
	if rollbackErr := store.FinishMergeRollback(t.Context(), a, recovery.Job); !errors.Is(rollbackErr, finalization.ErrStale) {
		t.Fatalf("rollback released a source before target retraction: %v", rollbackErr)
	}
	if _, deleteErr := bench.Raw.Doc(base + job.Target).Delete(t.Context()); deleteErr != nil {
		t.Fatal(deleteErr)
	}
	put(t, bench, base+"b", document{"status": "merging", "merge_job_id": "new-owner"})
	if rollbackErr := store.FinishMergeRollback(t.Context(), a, recovery.Job); rollbackErr != nil {
		t.Fatal(rollbackErr)
	}
	if read(t, bench, base+"a")["status"] != "completed" || read(t, bench, base+"b")["merge_job_id"] != "new-owner" {
		t.Fatal("rollback did not preserve new source ownership")
	}
}
