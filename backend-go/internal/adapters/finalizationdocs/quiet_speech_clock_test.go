package finalizationdocs

import (
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestPL158QuietDiscoveryAndAdmissionShareSpeechClock(t *testing.T) {
	t.Parallel()
	for _, name := range []string{"speech-only", "legacy-heartbeat", "speech-after-discovery"} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			store, bench, ref := quietFixture(t)
			speech := store.Clock.Now()
			const timeout = 30 * time.Second
			deadline := speech.Add(timeout)
			if name == "legacy-heartbeat" {
				row := read(t, bench, conversationPath)
				row["finished_at"] = speech.Add(time.Hour)
				put(t, bench, conversationPath, row)
			}
			setRecordingLease(t, bench, ref, deadline)
			a := queue.AdmittingForTest(t, ref.Owner)
			armed, err := store.ArmQuiet(t.Context(), a, ref, timeout.Seconds(), false)
			if err != nil || !armed.Due.Equal(deadline) {
				t.Fatalf("quiet deadline: %+v, %v", armed, err)
			}

			store.Clock = clock.Fixed{T: deadline}
			wake, err := store.WakeQuiet(t.Context(), a, armed)
			if err != nil || wake.Action != rules.QuietReady || !wake.Cutoff.Equal(speech) {
				t.Fatalf("quiet wake: %+v, %v", wake, err)
			}

			isStale := name == "speech-after-discovery"
			laterSpeech := speech.Add(time.Second)
			if isStale {
				row := read(t, bench, conversationPath)
				row["last_speech_at"] = laterSpeech
				put(t, bench, conversationPath, row)
				// Meet the new deadline while admitting against the old cutoff.
				store.Clock = clock.Fixed{T: laterSpeech.Add(timeout)}
			}
			before, err := bench.Raw.Doc(conversationPath).Get(t.Context())
			if err != nil {
				t.Fatal(err)
			}
			req := finalization.AdmissionRequest{
				Ref: ref, Trigger: rules.ServerRecovery, RequireExpiredLease: true,
				QuietGeneration: wake.Check.Generation, RecoveryCutoff: wake.Cutoff,
			}
			admit := func(request finalization.AdmissionRequest) finalization.Intent {
				t.Helper()
				intent, err := store.Admit(t.Context(), a, request, func(facts rules.AdmissionFacts) rules.AdmissionAction {
					return rules.Admission(request.Trigger, request.RecoveryCutoff, request.RequireExpiredLease, facts)
				})
				if err != nil {
					t.Fatal(err)
				}
				return intent
			}
			intent := admit(req)
			jobPath := jobs + "/" + finalization.JobID(ref, 1)
			if isStale {
				after, err := bench.Raw.Doc(conversationPath).Get(t.Context())
				if err != nil {
					t.Fatal(err)
				}
				if intent.JobID != "" || !after.UpdateTime.Equal(before.UpdateTime) || bench.Exists(t, jobPath) {
					t.Fatalf("stale wake changed custody: %+v, row %v", intent, after.Data())
				}
				quietJob := read(t, bench, jobs+"/"+finalization.QuietID(ref))
				if quietJob["status"] != quietWaiting || quietJob["dispatch_generation"] != wake.Check.Generation {
					t.Fatalf("stale admission lost its successor: %v", quietJob)
				}
				// Keep the row, clock and generation fixed. A current cutoff
				// must succeed, isolating the old cutoff as the refusal cause.
				req.RecoveryCutoff = laterSpeech
				intent = admit(req)
			}
			row := read(t, bench, conversationPath)
			if intent.JobID == "" || row["finalization_job_id"] != intent.JobID || row["status"] != "processing" || !bench.Exists(t, jobPath) {
				t.Fatalf("due speech did not bind a durable intent: %+v, row %v", intent, row)
			}
			quietJob := read(t, bench, jobs+"/"+finalization.QuietID(ref))
			if _, indexed := quietJob["reconcile_after_at"]; quietJob["status"] != quietDone || indexed {
				t.Fatalf("admission left the quiet check indexed: %v", quietJob)
			}
		})
	}
}
