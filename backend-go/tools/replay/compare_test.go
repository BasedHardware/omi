package main

import (
	"fmt"
	"strings"
	"testing"
	"time"
)

func TestCompareReportsNestedDiffsAndKeepsPresence(t *testing.T) {
	t.Parallel()
	raw := `[{"name":"nested","python":{"status":"completed","conversation":{
		"updated_at":"now","finalization_job_id":"py","structured":{"a/b":null,"list":[1,2]}},
		"effects":{},"derived_documents":{"memories/item":{"content":"one"}},"webhooks":[{"app":"first"}]},
		"go":{"status":"completed","conversation":{
		"finalization_job_id":"go","structured":{"list":[1.0,3],"til~de":true}},
		"effects":{},"derived_documents":{"memories/item":{"content":"two"}},"webhooks":[]}}]`
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

				"updated_at": map[string]any{"$timestamp": stamp.Format(time.RFC3339Nano)},
			},
			Webhooks: []any{map[string]any{"app": "fixture", "idempotency_key": fanout}},
		}
	}
	py := build("python", "python-fanout", start.Add(time.Second))
	goRun := build("go", "go-fanout", start.Add(2*time.Second))
	doc, ok := goRun.Document.(map[string]any)
	if !ok {
		t.Fatal("test observation needs a conversation object")
	}
	doc["fanout_key"] = "go-fanout"
	diffs := compareObservations(py, goRun)
	fanoutCompared := false
	for _, diff := range diffs {
		if diff.Path == "/fanout_key" {
			fanoutCompared = true
		}
		if diff.Reason == "" {
			t.Fatalf("verified binding and timestamp drift: %v", diff)
		}
	}
	if !fanoutCompared {
		t.Fatal("Python queue and Go conversation fanout IDs were not compared")
	}
	goRun = build("go", "go-fanout", start.Add(time.Hour))
	goRun.Admitted.Job = "wrong"
	goRun.Admitted.Fanout = "wrong"
	diffs = compareObservations(py, goRun)
	if len(diffs) < 3 {
		t.Fatalf("invalid evidence produced no drift: %v", diffs)
	}
	for _, diff := range diffs {
		if diff.Reason != "" {
			t.Fatalf("invalid binding or clock was allowed: %v", diff)
		}
	}
}

func TestProviderCallCountsPreventFalseParity(t *testing.T) {
	t.Parallel()
	baseline := observation{
		Status: "completed", Derived: map[string]any{}, Effects: map[string]any{},
		ProviderCalls: []string{"notes", "embeddings"},
	}
	for _, tc := range []struct {
		name  string
		calls []string
		path  string
		kind  string
	}{
		{name: "same calls in another order", calls: []string{"embeddings", "notes"}},
		{name: "extra invocation of one lane", calls: []string{"notes", "embeddings", "notes"}, path: "/provider_calls/notes", kind: "different_value"},
		{name: "missing embedding request", calls: []string{"notes"}, path: "/provider_calls/embeddings", kind: "missing_in_go"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			candidate := baseline
			candidate.ProviderCalls = tc.calls
			result, err := compare([]replayCase{{Name: tc.name, Python: &baseline, Go: &candidate}})
			if err != nil {
				t.Fatal(err)
			}
			diffs := result.Cases[0].Differences
			if tc.path == "" {
				if result.Matched != 1 || len(diffs) != 0 {
					t.Fatalf("same provider calls failed parity: %+v", diffs)
				}
				return
			}
			want := difference{Path: tc.path, Kind: tc.kind}
			if result.Matched != 0 || result.Unexplained != 1 || len(diffs) != 1 || diffs[0] != want {
				t.Fatalf("want one unexplained difference %+v, got %+v", want, diffs)
			}
		})
	}
}

func TestObservationsRequireExplicitEffectObjects(t *testing.T) {
	t.Parallel()
	const valid = `{"status":"completed","derived_documents":{},"effects":{}}`
	for _, tc := range []struct {
		partial string
		field   string
	}{
		{`"effects":{}`, "derived_documents"},
		{`"derived_documents":null,"effects":{}`, "derived_documents"},
		{`"derived_documents":[],"effects":{}`, "derived_documents"},
		{`"derived_documents":{}`, "effects"},
		{`"derived_documents":{},"effects":null`, "effects"},
		{`"derived_documents":{},"effects":[]`, "effects"},
	} {
		for _, reverse := range []bool{false, true} {
			invalid := fmt.Sprintf(`{"status":"completed",%s}`, tc.partial)
			left, right := valid, invalid
			if reverse {
				left, right = right, left
			}
			raw := fmt.Sprintf(`[{"name":"invalid","python":%s,"go":%s}]`, left, right)
			cases, err := decodeCases([]byte(raw))
			if err == nil {
				_, err = compare(cases)
			}
			if err == nil || !strings.Contains(err.Error(), tc.field) {
				t.Fatalf("wanted %s evidence error for %s, got %v", tc.field, raw, err)
			}
		}
	}

	raw := fmt.Sprintf(`[{"name":"empty","python":%s,"go":%s}]`, valid, valid)
	cases, err := decodeCases([]byte(raw))
	if err != nil {
		t.Fatal(err)
	}
	if result, err := compare(cases); err != nil || result.Matched != 1 {
		t.Fatalf("explicit empty objects must match: matches=%d, err=%v", result.Matched, err)
	}
}
