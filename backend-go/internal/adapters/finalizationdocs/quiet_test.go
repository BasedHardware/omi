package finalizationdocs

import (
	"math"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func quietFixture(t *testing.T) (Store, docstoretest.Bench, finalization.Ref) {
	t.Helper()
	store, bench, req := setup(t)
	put(t, bench, conversationPath, document{
		"status": "in_progress", "source": "omi", "last_speech_at": store.Clock.Now(),
		"transcript_segments": []document{{"text": "retained conversation"}},
		"external_data":       document{"recording_session_id": "session"},
	})
	return store, bench, req.Ref
}

func setRecordingLease(t *testing.T, bench docstoretest.Bench, ref finalization.Ref, expiry time.Time) {
	t.Helper()
	put(t, bench, "users/"+ref.Owner+"/recording_sessions/session", document{
		"uid": ref.Owner, "recording_session_id": "session", "conversation_id": ref.ID,
		"lifecycle_phase": "in_progress", "lease_expires_at": expiry,
	})
}

func TestF18QuietArmKeepsEarlierWakeAndKeyEvidence(t *testing.T) {
	t.Parallel()
	store, bench, ref := quietFixture(t)
	a := queue.AdmittingForTest(t, ref.Owner)
	first, err := store.ArmQuiet(t.Context(), a, ref, math.NaN(), true)
	if err != nil || first.Generation != 1 || !first.Due.Equal(store.Clock.Now().Add(120*time.Second)) {
		t.Fatalf("default wake: %+v %v", first, err)
	}
	later, err := store.ArmQuiet(t.Context(), a, ref, 40000, false)
	if err != nil || later != first || read(t, bench, jobs+"/"+finalization.QuietID(ref))["quiet_timeout_seconds"] != float64(14400) {
		t.Fatalf("later wake: %+v %v", later, err)
	}
	earlier, err := store.ArmQuiet(t.Context(), a, ref, -9, false)
	if err != nil || earlier.Generation != 2 || !earlier.Due.Equal(store.Clock.Now().Add(time.Second)) ||
		!field[bool](read(t, bench, conversationPath), "listen_finalization_requires_byok") {
		t.Fatalf("earlier wake or key evidence lost: %+v %v", earlier, err)
	}
}

func TestF19QuietSuccessorBeforeAdmissionAndReconnectFence(t *testing.T) {
	t.Parallel()
	store, bench, ref := quietFixture(t)
	start := store.Clock.Now()
	a := queue.AdmittingForTest(t, ref.Owner)
	armed, err := store.ArmQuiet(t.Context(), a, ref, 30, false)
	if err != nil {
		t.Fatal(err)
	}
	store.Clock = clock.Fixed{T: start.Add(30 * time.Second)}
	wake, err := store.WakeQuiet(t.Context(), a, armed)
	if err != nil || wake.Action != rules.QuietWait || wake.Check.Generation != 2 {
		t.Fatalf("unknown lease must reserve a successor: %+v %v", wake, err)
	}
	stale, err := store.WakeQuiet(t.Context(), a, armed)
	if err != nil || stale.Action != rules.QuietStale {
		t.Fatalf("stale wake: %+v %v", stale, err)
	}
	store.Clock = clock.Fixed{T: wake.Check.Due}
	setRecordingLease(t, bench, ref, store.Clock.Now())
	ready, err := store.WakeQuiet(t.Context(), a, wake.Check)
	if err != nil || ready.Action != rules.QuietReady || ready.Check.Generation != 3 {
		t.Fatalf("expired lease: %+v %v", ready, err)
	}
	setRecordingLease(t, bench, ref, store.Clock.Now().Add(time.Minute))
	req := finalization.AdmissionRequest{
		Ref: ref, Trigger: rules.ServerRecovery, RequireExpiredLease: true,
		QuietGeneration: ready.Check.Generation, RecoveryCutoff: ready.Cutoff,
	}
	intent, err := store.Admit(t.Context(), a, req, func(facts rules.AdmissionFacts) rules.AdmissionAction {
		return rules.Admission(req.Trigger, req.RecoveryCutoff, true, facts)
	})
	if err != nil || intent.JobID != "" || read(t, bench, jobs+"/"+finalization.QuietID(ref))["status"] != quietWaiting {
		t.Fatalf("reconnect lost the obligation: %+v %v", intent, err)
	}
}

func TestF19QuietAdmissionBindsAndRetiresCurrentCheck(t *testing.T) {
	t.Parallel()
	store, bench, ref := quietFixture(t)
	h := queuetest.Open(t, queuetest.Policy(), finalization.Declaration(Causes()...))
	svc := &finalization.Service{Queue: h.Store, Outbox: store, Quiet: store}
	check, err := svc.ArmQuiet(t.Context(), ref, 30, true)
	if err != nil {
		t.Fatal(err)
	}
	store.Clock = clock.Fixed{T: check.Due}
	svc.Quiet, svc.Outbox = store, store
	setRecordingLease(t, bench, ref, check.Due)
	wake, intent, err := svc.WakeQuiet(t.Context(), check, true)
	if err != nil || wake.Action != rules.QuietReady || !intent.RequiresBYOK || intent.JobID == "" {
		t.Fatalf("quiet handoff: %+v %+v %v", wake, intent, err)
	}
	if read(t, bench, jobs+"/"+finalization.QuietID(ref))["status"] != quietDone ||
		read(t, bench, conversationPath)["finalization_job_id"] != intent.JobID {
		t.Fatal("quiet retirement and binding did not converge")
	}
	job, err := h.Store.Get(t.Context(), intent.JobID)
	if err != nil || job.State != queue.StateBlocked {
		t.Fatalf("recovery lost BYOK custody: %+v %v", job, err)
	}
}
