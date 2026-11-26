package main

import (
	"strings"
	"testing"
	"time"
)

func TestProfileRefreshRequiresOneBackendStampWithinEachWindow(t *testing.T) {
	start := time.Date(2026, 11, 24, 13, 0, 0, 0, time.UTC)
	makeRun := func(offset time.Duration) *observation {
		stamp := start.Add(offset).Format(time.RFC3339Nano)
		return &observation{OwnerID: "u", Started: start, Finished: start.Add(time.Minute), ProviderCalls: []string{"memories"},
			ProfileWrites: []profileWrite{{Generated: stamp, Refreshed: stamp, Observed: start.Add(3 * time.Second)}},
			Derived: map[string]any{"users/u": map[string]any{"ai_user_profile": map[string]any{
				"generated_at": stamp, "refreshed_at": stamp, "source": "backend", "profile_text": "fixture",
			}}}}
	}
	for _, field := range []string{"", "different_payload", "different_stamps", "before_capture", "after_last_write", "second_write", "missing_trace", "stored_stamp_drift"} {
		py, candidate := makeRun(time.Second), makeRun(2*time.Second)
		profile := mustMap(objectField(candidate.Derived["users/u"], "ai_user_profile"))
		switch field {
		case "":
		case "different_payload":
			profile["profile_text"] = "different"
		case "different_stamps":
			profile["refreshed_at"] = start.Add(3 * time.Second).Format(time.RFC3339Nano)
		case "before_capture":
			stamp := start.Add(-time.Second).Format(time.RFC3339Nano)
			profile["generated_at"], profile["refreshed_at"] = stamp, stamp
			candidate.ProfileWrites[0].Generated, candidate.ProfileWrites[0].Refreshed = stamp, stamp
		case "after_last_write":
			candidate.ProfileWrites[0].Observed = start
		case "second_write":
			candidate.ProfileWrites = append(candidate.ProfileWrites, candidate.ProfileWrites[0])
		case "missing_trace":
			candidate.ProfileWrites = nil
		case "stored_stamp_drift":
			candidate.ProfileWrites[0].Generated = start.Format(time.RFC3339Nano)
		default:
			t.Fatalf("unknown mutation %q", field)
		}
		diffs := []difference{{Path: "/derived_documents/users~1u/ai_user_profile/generated_at", Kind: "different_value"}}
		reviewProfileRefreshClocks(diffs, py, candidate)
		if (diffs[0].Reason != "") != (field == "") {
			t.Errorf("mutation %q produced reason %q", field, diffs[0].Reason)
		}
	}
}

func TestUnprovenSyncWritesRemainGoGapsWhenSnapshotsMatch(t *testing.T) {
	start := time.Date(2026, 11, 24, 13, 0, 0, 0, time.UTC)
	stamp := start.Add(time.Second).Format(time.RFC3339Nano)
	profileRun := func() *observation {
		return &observation{
			OwnerID: "replay-integration-one-success", ConversationID: "integration-one-success",
			Started: start, Finished: start.Add(time.Minute), Admitted: &admission{Engine: "go"},
			Derived: map[string]any{"users/replay-integration-one-success": map[string]any{"ai_user_profile": map[string]any{
				"generated_at": stamp, "refreshed_at": stamp, "source": "backend", "profile_text": "fixture",
			}}},
		}
	}
	python, goRun := profileRun(), profileRun()
	var diffs []difference
	reviewRuledSyncWrites(&diffs, python, goRun)
	if len(diffs) != 1 || diffs[0].FailureReason != "profile_refresh_proof_failed" {
		t.Fatalf("missing profile write evidence passed on equal snapshots: %+v", diffs)
	}

	pythonTask, goTask := taskProofRun(strings.Repeat("A", 20)), taskProofRun(strings.Repeat("A", 20))
	goTask.Admitted = &admission{Engine: "go"}
	goTask.TaskWrites = nil
	diffs = nil
	reviewRuledSyncWrites(&diffs, pythonTask, goTask)
	for _, diff := range diffs {
		if diff.FailureReason == "task_vector_proof_failed" {
			return
		}
	}
	t.Fatalf("missing task write evidence passed on equal snapshots: %+v", diffs)
}
