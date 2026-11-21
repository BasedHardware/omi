package finalizationdocs

import (
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func setSyncRevision(t *testing.T, bench docstoretest.Bench, revision int64) {
	t.Helper()
	row := read(t, bench, conversationPath)
	row["sync_content_revision"] = revision
	put(t, bench, conversationPath, row)
}

func TestF35SyncRevisionQuietBoundaryAndRedispatchLimit(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	start := store.Clock.Now()
	beginClaim(t, store, g, claim)
	path := jobs + "/" + claim.Intent.JobID
	for i := int64(1); i <= 3; i++ {
		setSyncRevision(t, bench, i)
		delay, err := store.DeferSyncRevision(t.Context(), g, claim, i-1)
		if err != nil || delay != 30*time.Second {
			t.Fatalf("redispatch %d: %v, %v", i, delay, err)
		}
		job := read(t, bench, path)
		if job["dispatch_generation"] != i+1 || job["worker_claim_count"] != int64(0) {
			t.Fatalf("unexpected redispatch accounting: %v", job)
		}
		if err := store.Begin(t.Context(), g, claim); !errors.Is(err, queue.ErrLease) {
			t.Fatalf("stale claim: %v", err)
		}
		claim.Epoch++
		due := start.Add(time.Duration(i) * 30 * time.Second)
		store.Clock = clock.Fixed{T: due.Add(-time.Microsecond)}
		if err := store.Begin(t.Context(), g, claim); !errors.Is(err, errSyncWait) {
			t.Fatalf("early claim: %v", err)
		}
		store.Clock = clock.Fixed{T: due}
		beginClaim(t, store, g, claim)
	}
	setSyncRevision(t, bench, 4)
	if _, err := store.DeferSyncRevision(t.Context(), g, claim, 3); !errors.Is(err, errSyncWait) {
		t.Fatalf("fourth change: %v", err)
	}
	job := read(t, bench, path)
	if job["terminal_outcome"] != "stale" || job["dispatch_generation"] != int64(4) {
		t.Fatalf("unexpected retirement: %v", job)
	}
}

func TestF35SyncRevisionWaitRetiresAtAgeBound(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	start := store.Clock.Now()
	beginClaim(t, store, g, claim)
	setSyncRevision(t, bench, 1)
	if _, err := store.DeferSyncRevision(t.Context(), g, claim, 0); err != nil {
		t.Fatal(err)
	}
	claim.Epoch++
	store.Clock = clock.Fixed{T: start.Add(599 * time.Second)}
	beginClaim(t, store, g, claim)
	setSyncRevision(t, bench, 2)
	delay, err := store.DeferSyncRevision(t.Context(), g, claim, 1)
	if err != nil || delay != time.Second {
		t.Fatalf("did not cap wait at 600s: %v %v", delay, err)
	}
	claim.Epoch++
	store.Clock = clock.Fixed{T: start.Add(600 * time.Second)}
	beginClaim(t, store, g, claim)
	if read(t, bench, jobs+"/"+claim.Intent.JobID)["terminal_outcome"] != "stale" {
		t.Fatal("wait passed its age bound")
	}
}

func TestF35ManualRedrivePreservesGrantAndRejectsPriorEpoch(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	claim.BudgetRequeues = 1
	beginClaim(t, store, g, claim)
	state, err := store.DeadLetter(t.Context(), g, claim, CauseUnavailable, true)
	if err != nil || state != finalization.TerminalDeadLetter {
		t.Fatalf("dead letter: %v %v", state, err)
	}
	path := jobs + "/" + claim.Intent.JobID
	job := read(t, bench, path)
	job["attempt_count"], job["worker_claim_count"], job["task_retry_count"] = int64(5), int64(5), int64(4)
	put(t, bench, path, job)
	a := queue.AdmittingForTest(t, claim.Intent.Ref.Owner)
	for range 2 {
		if redriveErr := store.PrepareRedrive(t.Context(), a, claim.Intent, claim.Epoch, 1); redriveErr != nil {
			t.Fatal(redriveErr)
		}
	}
	job = read(t, bench, path)
	if job["dispatch_generation"] != int64(2) || job["status"] != queued || job["budget_requeue_count"] != int64(1) ||
		job["attempt_count"] != int64(0) || job["worker_claim_count"] != int64(0) || job["task_retry_count"] != int64(0) {
		t.Fatalf("incorrect redrive state: %v", job)
	}
	if earlier := store.Begin(t.Context(), g, claim); !errors.Is(earlier, queue.ErrLease) {
		t.Fatalf("old epoch reclaimed redrive: %v", earlier)
	}
	claim.Epoch++
	beginClaim(t, store, g, claim)
}
