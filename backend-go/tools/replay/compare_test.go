package main

import (
	"strings"
	"testing"
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
	if result.Expected != 1 || result.Unexplained != 6 || result.Matched != 0 {
		t.Fatalf("unexpected comparison: %+v", result)
	}
	got := make(map[string]string)
	for _, diff := range result.Cases[0].Differences {
		got[diff.Path] = diff.Kind
	}
	want := map[string]string{
		"/conversation/updated_at":                  "missing_in_go",
		"/conversation/structured/a~1b":             "missing_in_go",
		"/conversation/structured/til~0de":          "missing_in_python",
		"/conversation/structured/list/1":           "different_value",
		"/derived_documents/memories~1item/content": "different_value",
		"/webhooks/0":                               "missing_in_go",
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
