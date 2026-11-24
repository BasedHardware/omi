package finalizationdocs

import (
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func admitted(t *testing.T) (Store, docstoretest.Bench, queue.Guarded, finalization.Claim) {
	t.Helper()
	store, bench, req := setup(t)
	intent, err := store.Admit(t.Context(), queue.AdmittingForTest(t, req.Ref.Owner), req, decide)
	if err != nil || intent.JobID == "" {
		t.Fatalf("admit: %+v %v", intent, err)
	}
	return store, bench, queue.GuardedForTest(t, req.Ref.Owner, intent.JobID), finalization.Claim{Intent: intent, Epoch: 8}
}

func beginClaim(t *testing.T, store Store, g queue.Guarded, claim finalization.Claim) {
	t.Helper()
	if _, err := store.Begin(t.Context(), g, claim); err != nil {
		t.Fatal(err)
	}
}

func completedRow(t *testing.T, bench docstoretest.Bench) {
	t.Helper()
	row := read(t, bench, conversationPath)
	row["status"] = "completed"
	row["structured"] = document{"title": "Latest title", "overview": "Current overview"}
	row["sync_content_revision"] = int64(9)
	put(t, bench, conversationPath, row)
}

func TestF06TakeoverAndForeignLeaseFenceOldEpochs(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	path := jobs + "/" + claim.Intent.JobID
	job := read(t, bench, path)
	job["status"], job["lease_epoch"], job["lease_expires_at"] = leased, int64(80), time.Unix(2100, 0)
	// Use an unstamped foreign lease to exercise takeover without corrupting a
	// shard counter that another dispatcher would update in its own claim.
	delete(job, "projection_generation")
	put(t, bench, path, job)
	if _, err := store.Begin(t.Context(), g, claim); !errors.Is(err, errForeignLease) {
		t.Fatalf("accepted live foreign lease: %v", err)
	}
	job["lease_expires_at"] = time.Unix(1999, 0)
	put(t, bench, path, job)
	beginClaim(t, store, g, claim)
	beginClaim(t, store, g, claim)
	newer := claim
	newer.Epoch++
	beginClaim(t, store, g, newer)
	reconcile := newer
	reconcile.Epoch++
	reconcile.Reconcile = true
	beginClaim(t, store, g, reconcile)
	if _, err := store.Fence(t.Context(), g, claim); !errors.Is(err, queue.ErrLease) {
		t.Fatalf("old epoch wrote after takeover: %v", err)
	}
	job = read(t, bench, path)
	if job["worker_claim_count"] != int64(2) || job["lease_epoch"] != int64(83) || job["lease_counts_worker_attempt"] != false || job["status"] != leased {
		t.Fatalf("incorrect accepted-claim accounting: %v", job)
	}
}

func TestF06NewerDispatchGenerationRefusesTheEarlierQueueIntent(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	path := jobs + "/" + claim.Intent.JobID
	job := read(t, bench, path)
	job["dispatch_generation"] = int64(2)
	put(t, bench, path, job)
	if _, err := store.Begin(t.Context(), g, claim); !errors.Is(err, errForeignGeneration) {
		t.Fatalf("began stale queue intent: %v", err)
	}
	if read(t, bench, path)["status"] != queued {
		t.Fatal("stale intent mutated the newer dispatch")
	}
}

func TestF11DiscardOrAccountEraseRefusesFanout(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	beginClaim(t, store, g, claim)
	completedRow(t, bench)
	bench.Mark(t, claim.Intent.Ref.Owner, map[string]any{"wipe_status": "pending"})
	if _, err := store.ClaimFanout(t.Context(), g, claim); !errors.Is(err, docstore.ErrOwnerDeleting) {
		t.Fatalf("account marker did not hold: %v", err)
	}
	bench.Mark(t, claim.Intent.Ref.Owner, map[string]any{"wipe_status": "cancelled"})
	row := read(t, bench, conversationPath)
	row["discarded"] = true
	put(t, bench, conversationPath, row)
	got, err := store.ClaimFanout(t.Context(), g, claim)
	if err != nil || got.State != finalization.FanoutStale ||
		read(t, bench, jobs+"/"+claim.Intent.JobID)["terminal_outcome"] != "stale" {
		t.Fatalf("discard was not durably fenced: %+v %v", got, err)
	}
}

func TestF15AndF38CommitWinsAndTerminalProjectionIsExactlyOnce(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	beginClaim(t, store, g, claim)
	completedRow(t, bench)
	fanout, err := store.ClaimFanout(t.Context(), g, claim)
	if err != nil || fanout.State != finalization.FanoutAcquired || fanout.Key == "" || fanout.Conversation.Notes.Title != "Latest title" {
		t.Fatalf("claim did not return the committed snapshot: %+v %v", fanout, err)
	}
	if _, err := store.CompleteFanout(t.Context(), g, claim, true); err != nil {
		t.Fatal(err)
	}
	claim.Epoch++
	beginClaim(t, store, g, claim)
	results := make(chan error, 2)
	for range 2 {
		go func() {
			state, closeErr := store.DeadLetter(t.Context(), g, claim, CauseRejected, false)
			if closeErr == nil && state != finalization.TerminalDeliveryDropped {
				closeErr = fmt.Errorf("committed fanout lost to terminal state %v", state)
			}
			results <- closeErr
		}()
	}
	if first, second := <-results, <-results; first != nil || second != nil {
		t.Fatalf("closure: %v %v", first, second)
	}
	job := read(t, bench, jobs+"/"+claim.Intent.JobID)
	shardPath := fmt.Sprintf("%s/%s-%02d", projectionCollection, projectionGeneration, projectionShard(claim.Intent.JobID))
	shard := read(t, bench, shardPath)
	if job["terminal_outcome"] != "success" || job["reconcile_after_at"] != nil ||
		shard["accepted"] != int64(1) || shard["leased"] != int64(0) || shard["success"] != int64(1) || shard["failure"] != nil {
		t.Fatalf("closure: job %v projection %v", job, shard)
	}
}

func TestF17DeadLetterClosesBindingPreservesSpeechAndWritesAttention(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	beginClaim(t, store, g, claim)
	row := read(t, bench, conversationPath)
	row["transcript_segments"] = []document{{"text": "owner can still read this"}}
	put(t, bench, conversationPath, row)
	state, err := store.DeadLetter(t.Context(), g, claim, CauseUnavailable, true)
	if err != nil || state != finalization.TerminalDeadLetter {
		t.Fatalf("terminal: %v %v", state, err)
	}
	row = read(t, bench, conversationPath)
	if row["status"] != "completed" || row["finalization_status"] != deadLetter ||
		!field[bool](row, "summary_retryable") || len(field[[]any](row, "transcript_segments")) != 1 {
		t.Fatalf("processing row did not close safely: %v", row)
	}
	items, err := bench.Raw.Doc("users/" + claim.Intent.Ref.Owner).Collection("processing_attention_items").Documents(t.Context()).GetAll()
	if err != nil || len(items) != 1 || items[0].Data()["failure_code"] != string(CauseUnavailable) {
		t.Fatalf("attention: %v %v", len(items), err)
	}
}

func TestF38UnstampedLegacyTerminalDoesNotChangeTheProjection(t *testing.T) {
	t.Parallel()
	store, bench, req := setup(t)
	id := finalization.JobID(req.Ref, 1)
	put(t, bench, jobs+"/"+id, document{
		"uid": req.Ref.Owner, "conversation_id": req.Ref.ID, "finalization_revision": int64(1), "status": queued,
	})
	intent, err := store.Admit(t.Context(), queue.AdmittingForTest(t, req.Ref.Owner), req, decide)
	if err != nil || intent.JobID != id {
		t.Fatalf("attach: %+v %v", intent, err)
	}
	g := queue.GuardedForTest(t, req.Ref.Owner, id)
	claim := finalization.Claim{Intent: intent, Epoch: 1}
	beginClaim(t, store, g, claim)
	if _, deleteErr := bench.Raw.Doc(conversationPath).Delete(t.Context()); deleteErr != nil {
		t.Fatal(deleteErr)
	}
	state, err := store.Fence(t.Context(), g, claim)
	if err != nil || state != finalization.TerminalStale || read(t, bench, jobs+"/"+id)["terminal_outcome"] != "stale" {
		t.Fatalf("legacy terminal was lost: %v %v", state, err)
	}
	shardPath := fmt.Sprintf("%s/%s-%02d", projectionCollection, projectionGeneration, projectionShard(id))
	if bench.Exists(t, shardPath) {
		t.Fatal("legacy terminal contributed to the current generation")
	}
}

func TestF32ConversationTombstoneRefusesFanoutAndRedrive(t *testing.T) {
	t.Parallel()
	t.Run("fanout", func(t *testing.T) {
		t.Parallel()
		store, bench, g, claim := admitted(t)
		beginClaim(t, store, g, claim)
		completedRow(t, bench)
		putDeleteIntent(t, bench, claim.Intent.Ref)
		got, err := store.ClaimFanout(t.Context(), g, claim)
		if err != nil || got.State != finalization.FanoutStale {
			t.Fatalf("tombstoned row reached fanout: %+v %v", got, err)
		}
	})
	t.Run("redrive", func(t *testing.T) {
		t.Parallel()
		store, bench, g, claim := admitted(t)
		beginClaim(t, store, g, claim)
		if state, err := store.DeadLetter(t.Context(), g, claim, CauseUnavailable, true); err != nil || state != finalization.TerminalDeadLetter {
			t.Fatalf("dead letter: %v %v", state, err)
		}
		putDeleteIntent(t, bench, claim.Intent.Ref)
		a := queue.AdmittingForTest(t, claim.Intent.Ref.Owner)
		if err := store.PrepareRedrive(t.Context(), a, claim.Intent, claim.Epoch, 0); !errors.Is(err, queue.ErrState) {
			t.Fatalf("tombstoned row was redriven: %v", err)
		}
		if job := read(t, bench, jobs+"/"+claim.Intent.JobID); job["status"] != deadLetter {
			t.Fatalf("redrive mutated the parked job: %v", job)
		}
	})
}

func putDeleteIntent(t *testing.T, bench docstoretest.Bench, ref finalization.Ref) {
	t.Helper()
	put(t, bench, "users/"+ref.Owner+"/deleted_conversations/"+ref.ID, map[string]any{"conversation_id": ref.ID})
}
