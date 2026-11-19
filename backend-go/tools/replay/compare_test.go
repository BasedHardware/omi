package main

import (
	"strings"
	"testing"
	"time"
)

func TestCompareReportsNestedDiffsAndKeepsPresence(t *testing.T) {
	t.Parallel()
	raw := `[{"name":"nested","python":{"status":"completed","conversation":{
		"updated_at":"now","finalization_job_id":"py","structured":{"a/b":null,"list":[1,2]}},
		"derived_documents":{"memories/item":{"content":"one"}},"webhooks":[{"app":"first"}]},
		"go":{"status":"completed","conversation":{
		"finalization_job_id":"go","structured":{"list":[1.0,3],"til~de":true}},
		"derived_documents":{"memories/item":{"content":"two"}},"webhooks":[]}}]`
	cases, err := decodeCases([]byte(raw))
	if err != nil {
		t.Fatal(err)
	}
	result, err := compare(cases)
	if err != nil {
		t.Fatal(err)
	}
	if result.Expected != 0 || result.Unexplained != 7 || result.Matched != 0 {
		t.Fatalf("unexpected comparison: %+v", result)
	}
	got := make(map[string]string)
	for _, diff := range result.Cases[0].Differences {
		got[diff.Path] = diff.Kind
	}
	want := map[string]string{
		"/conversation/finalization_job_id":         "different_value",
		"/conversation/updated_at":                  "missing_in_go",
		"/conversation/structured/a~1b":             "missing_in_go",
		"/conversation/structured/til~0de":          "missing_in_python",
		"/conversation/structured/list/1":           "different_value",
		"/derived_documents/memories~1item/content": "different_value",
		"/webhooks/first":                           "missing_in_go",
	}
	for path, kind := range want {
		if got[path] != kind {
			t.Errorf("%s: got %q, want %q", path, got[path], kind)
		}
	}
}

func TestCompareRejectsInvalidEvidence(t *testing.T) {
	t.Parallel()
	if _, err := decodeCases([]byte("[] []")); err == nil {
		t.Fatal("accepted trailing observations")
	}
	if _, err := compare([]replayCase{{Name: "missing"}}); err == nil || !strings.Contains(err.Error(), "observation") {
		t.Fatalf("missing observation: %v", err)
	}
}

func TestCompareCountsExecutionErrors(t *testing.T) {
	t.Parallel()
	result, err := compare([]replayCase{{Name: "error", Errors: map[string]string{"go": "TimeoutError"}}})
	if err != nil || result.Failed != 1 || result.Matched != 0 {
		t.Fatalf("execution error counted as parity: %+v, %v", result, err)
	}
}

func TestCompareDifferencesWithIncompatibleJSONShapes(t *testing.T) {
	t.Parallel()
	for _, pair := range [][2]any{
		{map[string]any{}, nil}, {[]any{}, nil}, {nil, []any{}},
		{true, []any{}}, {[]any{}, "scalar"}, {map[string]any{}, []any{}},
	} {
		var differences []difference
		compareValue(&differences, "/conversation", pair[0], pair[1])
		if len(differences) != 1 || differences[0].Kind != "different_value" {
			t.Fatalf("shape mismatch produced %v", differences)
		}
	}
}

func TestCompareOnlyExcusesVerifiedBindingsAndClocks(t *testing.T) {
	t.Parallel()
	start := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
	build := func(job, fanout string, stamp time.Time) *observation {
		return &observation{
			Status: "completed", UpdatedAtChanged: true, QueueFanout: fanout, Admitted: &admission{Job: job, Fanout: fanout},
			Started: start, Finished: start.Add(time.Minute),
			Document: map[string]any{
				"finalization_job_id": job,
				"fanout_key":          fanout,
				"updated_at":          map[string]any{"$timestamp": stamp.Format(time.RFC3339Nano)},
			},
			Webhooks: []any{map[string]any{"app": "fixture", "idempotency_key": fanout}},
		}
	}
	py := build("python", "python-fanout", start.Add(time.Second))
	goRun := build("go", "go-fanout", start.Add(2*time.Second))
	for _, diff := range compareObservations(py, goRun) {
		if diff.Reason == "" {
			t.Fatalf("verified binding and timestamp drift: %v", diff)
		}
	}
	goRun = build("go", "go-fanout", start.Add(time.Hour))
	goRun.Admitted.Job = "wrong"
	goRun.Admitted.Fanout = "wrong"
	diffs := compareObservations(py, goRun)
	if len(diffs) < 3 {
		t.Fatalf("invalid evidence produced no drift: %v", diffs)
	}
	for _, diff := range diffs {
		if diff.Reason != "" {
			t.Fatalf("invalid binding or clock was allowed: %v", diff)
		}
	}
}
