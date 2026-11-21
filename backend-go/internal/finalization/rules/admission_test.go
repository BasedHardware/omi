package rules

import (
	"testing"
	"time"
)

func TestF01ProcessingTriggerPolicy(t *testing.T) {
	t.Parallel()
	want := map[Trigger]Mode{
		CaptureEnd: {false, false, true}, ClientFinalize: {true, false, true},
		SyncUpdate: {true, true, true}, FirstOpen: {true, false, false},
		BacklogChoice: {true, true, false}, UserReprocess: {true, true, false},
		Merge: {true, false, false}, SmartMerge: {true, true, false},
		CaptureGroup: {true, true, false}, ScreenEvidence: {true, true, false},
		ServerRecovery: {true, true, false}, SilentBackfill: {true, true, false},
		HistoricalOpen: {true, true, false},
	}
	for trigger, expected := range want {
		if mode, ok := ProcessingMode(trigger); !ok || mode != expected {
			t.Errorf("%s: got %+v, %v; want %+v", trigger, mode, ok, expected)
		}
	}
	if _, ok := ProcessingMode("unrecognized"); ok {
		t.Fatal("unknown trigger accepted")
	}
}

func TestF02NewRevisionRequiresEligibleLifecycle(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name  string
		facts AdmissionFacts
		want  AdmissionAction
	}{
		{"in-progress", AdmissionFacts{Status: InProgress, HasContent: true}, BindNext},
		{"processing-with-job", AdmissionFacts{Status: Processing, HasContent: true, ExistingJob: true}, UseBound},
		{"processing-orphan", AdmissionFacts{Status: Processing, HasContent: true}, Refuse},
		{"completed", AdmissionFacts{Status: Completed, HasContent: true}, Refuse},
		{"failed", AdmissionFacts{Status: Failed, HasContent: true}, Refuse},
		{"discarded", AdmissionFacts{Status: InProgress, HasContent: true, Discarded: true}, Refuse},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := Admission(CaptureEnd, time.Time{}, false, tc.facts); got != tc.want {
				t.Fatalf("got %v; want %v", got, tc.want)
			}
		})
	}
}

func TestF03RecoveryRevalidatesCurrentFacts(t *testing.T) {
	t.Parallel()
	cutoff := time.Unix(100, 0)
	eligible := AdmissionFacts{
		Status: InProgress, HasContent: true, RecoverySource: true, RecoveryContentBounded: true,
		QuietDeadlinePassed: true, LastSpeech: cutoff, RecordingLease: LeaseExpired,
		BackfillEligible: true, BackfillOwnerAvailable: true,
	}
	if got := Admission(ServerRecovery, cutoff, true, eligible); got != BindNext {
		t.Fatalf("quiet recovery at cutoff: %v", got)
	}
	for name, change := range map[string]func(*AdmissionFacts){
		"retained tail":  func(f *AdmissionFacts) { f.LastSpeech = cutoff.Add(time.Nanosecond) },
		"active session": func(f *AdmissionFacts) { f.RecordingLease = LeaseActive },
		"unknown lease":  func(f *AdmissionFacts) { f.RecordingLease = LeaseUnknown },
		"account wipe":   func(f *AdmissionFacts) { f.OwnerDeleting = true },
		"dead letter":    func(f *AdmissionFacts) { f.HasBinding = true },
		"no content":     func(f *AdmissionFacts) { f.HasContent = false },
		"protected":      func(f *AdmissionFacts) { f.Protected = true },
		"wrong source":   func(f *AdmissionFacts) { f.RecoverySource = false },
		"quiet deadline": func(f *AdmissionFacts) { f.QuietDeadlinePassed = false },
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			current := eligible
			change(&current)
			if got := Admission(ServerRecovery, cutoff, true, current); got != Refuse {
				t.Fatalf("quiet recovery admitted: %v", got)
			}
		})
	}
	eligible.BackfillOwnerAvailable = false
	if got := Admission(SilentBackfill, cutoff, false, eligible); got != Refuse {
		t.Fatalf("parallel silent backfill admitted: %v", got)
	}
}
