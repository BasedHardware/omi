package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestGoOnlyReceiptsRequireBoundGoEvidenceAndNoPythonCopies(t *testing.T) {
	py, goRun := ruleRun(), ruleRun()
	goRun.Admitted = &admission{Job: "job-go", Fanout: "fan-go", Engine: "go", OwnerEpoch: 3, Revision: 2}
	goRun.QueueFanout = "fan-go"
	goRun.Document = map[string]any{
		"finalization_engine": "go", "finalization_job_id": "job-go", "finalization_owner_epoch": json.Number("3"),
		"finalization_revision": json.Number("2"), "fanout_key": "fan-go",
		"go_sync_minimum_discarded": false, "go_sync_minimum_revision": json.Number("4"),
		"sync_content_revision": json.Number("4"), "discarded": false,
	}
	py.Document = map[string]any{"discarded": false, "sync_content_revision": json.Number("4")}
	diffs := compareObservations(py, goRun)
	if !hasKindPath(diffs, "missing_in_python", "/conversation/finalization_job_id") {
		t.Fatalf("Go job pointer must remain an unexplained go_gap: %+v", diffs)
	}
	for _, path := range []string{"/conversation/finalization_engine", "/conversation/go_sync_minimum_revision"} {
		if !hasReason(diffs, path) {
			t.Fatalf("missing executable comparison reason for %s: %+v", path, diffs)
		}
	}

	mustMap(goRun.Document)["finalization_owner_epoch"] = json.Number("4")
	diffs = compareObservations(py, goRun)
	if !hasUnexplained(diffs) || !hasKindPath(diffs, "invalid_binding", "/go/conversation/finalization_engine") {
		t.Fatalf("wrong owner epoch was excused: %+v", diffs)
	}

	mustMap(goRun.Document)["finalization_owner_epoch"] = json.Number("3")
	mustMap(goRun.Document)["go_sync_minimum_revision"] = json.Number("5")
	diffs = compareObservations(py, goRun)
	if !hasUnexplained(diffs) || !hasKindPath(diffs, "invalid_binding", "/go/conversation/go_sync_minimum_revision") {
		t.Fatalf("minimum receipt bound to another revision was excused: %+v", diffs)
	}

	mustMap(goRun.Document)["go_sync_minimum_revision"] = json.Number("4")
	mustMap(goRun.Document)["finalization_job_id"] = "wrong-job"
	diffs = compareObservations(py, goRun)
	if !hasUnexplained(diffs) || !hasKindPath(diffs, "invalid_binding", "/go/conversation/finalization_job_id") {
		t.Fatalf("Go job ID not bound to admitted job was excused: %+v", diffs)
	}
	mustMap(goRun.Document)["finalization_job_id"] = "job-go"
	py.Document = map[string]any{"finalization_engine": "python"}
	diffs = compareObservations(py, goRun)
	if !hasKindPath(diffs, "invalid_binding", "/python/conversation/finalization_engine") {
		t.Fatalf("Python row carrying Go fence metadata was not rejected: %+v", diffs)
	}

	missingPy, missingGo := ruleRun(), ruleRun()
	missingGo.Admitted = &admission{Job: "job-go", Fanout: "fan-go", Engine: "go", OwnerEpoch: 3, Revision: 2}
	missingGo.QueueFanout = "fan-go"
	missingGo.Document = map[string]any{"finalization_job_id": "job-go", "fanout_key": "fan-go"}
	missingDiffs := compareObservations(missingPy, missingGo)
	if !hasKindPath(missingDiffs, "invalid_binding", "/go/conversation/finalization_engine") ||
		!hasKindPath(missingDiffs, "invalid_binding", "/go/conversation/finalization_owner_epoch") ||
		!hasKindPath(missingDiffs, "invalid_binding", "/go/conversation/finalization_revision") {
		t.Fatalf("missing Go ownership fence fields were not rejected: %+v", missingDiffs)
	}
}

func TestHomeTokenFailureReasonNamesBrokenPrecondition(t *testing.T) {
	fixture := homeFixtures()[0]
	py, goRun := ruleRun(), ruleRun()
	homeToken(py, fixture, "123e4567e89b42d3a456426614174000")
	homeToken(goRun, fixture, "223e4567e89b42d3a456426614174000")
	mustMap(goRun.Document)["home_prepared_source_version"] = "323e4567e89b42d3a456426614174000"
	diffs := compareObservations(py, goRun)
	encoded, err := json.Marshal(diffs)
	if err != nil {
		t.Fatal(err)
	}
	for _, diff := range diffs {
		if diff.Path == "go/conversation/home_source_version" {
			if diff.Kind != "invalid_token_binding" || diff.FailureReason != "prepared_source_version_mismatch" {
				t.Fatalf("unexpected per-slot reason: %+v", diff)
			}
			if !strings.Contains(string(encoded), `"failure_reason":"prepared_source_version_mismatch"`) {
				t.Fatalf("failure reason was not serialized into the row: %s", encoded)
			}
			return
		}
	}
	t.Fatalf("missing invalid token slot row: %+v", diffs)
}

func TestReleasedMemoryTokenUsesFreshUUIDRule(t *testing.T) {
	path := "users/u/memory_state/released_memory_changes_v1"
	py, goRun := ruleRun(), ruleRun()
	py.OwnerID, goRun.OwnerID = "u", "u"
	py.Derived[path] = map[string]any{"token": "123e4567e89b42d3a456426614174000"}
	goRun.Derived[path] = map[string]any{"token": "223e4567e89b42d3a456426614174000"}
	diffs := compareObservations(py, goRun)
	if hasUnexplained(diffs) || !hasReason(diffs, "/token") {
		t.Fatalf("fresh release token values were not approved: %+v", diffs)
	}
	mustMap(goRun.Derived[path])["token"] = "not-a-uuid"
	diffs = compareObservations(py, goRun)
	for _, diff := range diffs {
		if diff.Path == "go/derived_documents/users~1u~1memory_state~1released_memory_changes_v1/token" {
			if diff.FailureReason != "not_uuidv4_hex" {
				t.Fatalf("invalid release token lacks its precondition reason: %+v", diff)
			}
			return
		}
	}
	t.Fatalf("invalid release token did not produce an evidence row: %+v", diffs)
}

func hasKindPath(diffs []difference, kind, path string) bool {
	for _, diff := range diffs {
		if diff.Kind == kind && diff.Path == path {
			return true
		}
	}
	return false
}
