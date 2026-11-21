package finalizationdocs

import (
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

const conversationPath = "users/fixture-owner/conversations/fixture-conversation"

func setup(t *testing.T) (Store, docstoretest.Bench, finalization.AdmissionRequest) {
	t.Helper()
	bench := docstoretest.Open(t)
	put(t, bench, conversationPath, document{"status": "in_progress", "has_content": true})
	req := finalization.AdmissionRequest{
		Ref: finalization.Ref{Owner: "fixture-owner", ID: "fixture-conversation"}, Trigger: rules.CaptureEnd,
	}
	return Store{Docs: bench.Store, Clock: clock.Fixed{T: time.Unix(2000, 0)}}, bench, req
}

func put(t *testing.T, bench docstoretest.Bench, path string, row document) {
	t.Helper()
	if _, err := bench.Raw.Doc(path).Set(t.Context(), row); err != nil {
		t.Fatal(err)
	}
}

func read(t *testing.T, bench docstoretest.Bench, path string) document {
	t.Helper()
	snapshot, err := bench.Raw.Doc(path).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	return snapshot.Data()
}

func decide(facts rules.AdmissionFacts) rules.AdmissionAction {
	return rules.Admission(rules.CaptureEnd, time.Time{}, false, facts)
}

func TestF02ConcurrentFirestoreAdmissionCommitsSingleBindingAndProjection(t *testing.T) {
	t.Parallel()
	store, bench, req := setup(t)
	type result struct {
		intent finalization.Intent
		err    error
	}
	a := queue.AdmittingForTest(t, req.Ref.Owner)
	results := make(chan result, 2)
	for range 2 {
		go func() {
			intent, err := store.Admit(t.Context(), a, req, decide)
			results <- result{intent, err}
		}()
	}
	first, second := <-results, <-results
	id := finalization.JobID(req.Ref, 1)
	if first.err != nil || second.err != nil || first.intent != second.intent || first.intent.JobID != id {
		t.Fatalf("admissions: %+v, %+v", first, second)
	}
	conversation := read(t, bench, conversationPath)
	job := read(t, bench, jobs+"/"+id)
	shard := read(t, bench, fmt.Sprintf("%s/%s-%02d", projectionCollection, projectionGeneration, projectionShard(id)))
	if conversation["finalization_job_id"] != id || conversation["status"] != "processing" ||
		job["status"] != queued || job["dispatch_generation"] != int64(1) ||
		shard["accepted"] != int64(1) || shard["queued"] != int64(1) {
		t.Fatalf("mismatched commit: %v %v %v", conversation, job, shard)
	}
}

func TestF02ReattachPreservesTheOriginalIntent(t *testing.T) {
	t.Parallel()
	store, bench, req := setup(t)
	id := finalization.JobID(req.Ref, 1)
	put(t, bench, jobs+"/"+id, document{
		"uid": req.Ref.Owner, "conversation_id": req.Ref.ID, "finalization_revision": int64(1),
		"status": blocked, "requires_byok": true, "force_process": true,
	})
	intent, err := store.Admit(t.Context(), queue.AdmittingForTest(t, req.Ref.Owner), req, decide)
	if err != nil || intent.JobID != id || !intent.RequiresBYOK || intent.Trigger != rules.ClientFinalize {
		t.Fatalf("reattach: %+v %v", intent, err)
	}
	conversation := read(t, bench, conversationPath)
	if conversation["finalization_job_id"] != id || conversation["finalization_status"] != blocked {
		t.Fatalf("binding: %v", conversation)
	}
	shardPath := fmt.Sprintf("%s/%s-%02d", projectionCollection, projectionGeneration, projectionShard(id))
	if bench.Exists(t, shardPath) {
		t.Fatal("reattaching an unstamped legacy job changed the projection")
	}
}

func TestF04DispatchFailureCanReplayCommittedFirestoreIntent(t *testing.T) {
	t.Parallel()
	store, bench, req := setup(t)
	bad := queuetest.Open(t, queuetest.Policy())
	s := &finalization.Service{Queue: bad.Store, Outbox: store}
	req.RequiresBYOK = true
	intent, err := s.Admit(t.Context(), req)
	if !errors.Is(err, queue.ErrUndeclared) || !bench.Exists(t, jobs+"/"+intent.JobID) {
		t.Fatalf("failed dispatch lost its intent: %+v, %v", intent, err)
	}
	h := queuetest.Open(t, queuetest.Policy(), finalization.Declaration())
	s.Queue = h.Store
	job, err := s.Dispatch(t.Context(), intent)
	if err != nil || job.State != queue.StateBlocked {
		t.Fatalf("replay did not park for BYOK: %+v, %v", job, err)
	}
}

func TestF32DeletionBarrierAndWrongTenantMakeNoWrites(t *testing.T) {
	t.Parallel()
	store, bench, req := setup(t)
	bench.Mark(t, req.Ref.Owner, map[string]any{"wipe_status": "pending"})
	for _, tc := range []struct {
		owner string
		want  error
	}{
		{req.Ref.Owner, docstore.ErrOwnerDeleting},
		{"wrong-owner", docstore.ErrOwnerMismatch},
	} {
		_, err := store.Admit(t.Context(), queue.AdmittingForTest(t, tc.owner), req, decide)
		if !errors.Is(err, tc.want) {
			t.Fatalf("got %v; want %v", err, tc.want)
		}
	}
	if read(t, bench, conversationPath)["status"] != "in_progress" || bench.Exists(t, jobs+"/"+finalization.JobID(req.Ref, 1)) {
		t.Fatal("refused admission mutated durable state")
	}
}
