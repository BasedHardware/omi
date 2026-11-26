package main

import (
	"encoding/json"
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

func TestOperationTableSurvivesValueStripping(t *testing.T) {
	result, err := compare([]replayCase{{
		Name: "operation-overage",
		Python: &observation{
			Status: "completed", Derived: map[string]any{}, Effects: map[string]any{},
			Cost: replayCost{Firestore: firestoreOperations{DocumentReads: 2, QueryDocuments: 1, Writes: 2, Deletes: 1}},
		},
		Go: &observation{
			Status: "completed", Derived: map[string]any{}, Effects: map[string]any{},
			Cost: replayCost{Firestore: firestoreOperations{DocumentReads: 4, Writes: 4, Deletes: 1}},
			FirestoreOperationSources: map[string]operationSource{
				"users/u/episode_links/c": {Reads: 3, Writes: 1},
				"users/u/conversations/c": {Reads: 1, Writes: 3, Deletes: 1},
			},
		},
	}})
	if err != nil {
		t.Fatal(err)
	}
	if len(result.OperationTable) != 1 {
		t.Fatalf("got %d operation rows", len(result.OperationTable))
	}
	row := result.OperationTable[0]
	if row.PythonReads != 3 || row.PythonWrites != 2 || row.PythonDeletes != 1 ||
		row.GoReads != 4 || row.GoWrites != 4 || row.GoDeletes != 1 ||
		row.Difference != 3 || row.Label != "go_gap:ops" {
		t.Fatalf("unexpected operation row: %+v", row)
	}
	if len(row.GoTopOperationSources) != 2 || row.GoTopOperationSources[0].DocumentPath != "users/u/conversations/c" {
		t.Fatalf("Go operation sources were not ranked: %+v", row.GoTopOperationSources)
	}
	stripReportValues(&result)
	if result.OperationTable[0].Label != "go_gap:ops" || len(result.OperationTable[0].GoTopOperationSources) != 2 {
		t.Fatalf("value stripping removed the operation report: %+v", result.OperationTable[0])
	}
}

func TestCompareRetainsValueFreeHomeReceiptTraceWhenStrippingObservations(t *testing.T) {
	result, err := compare([]replayCase{{
		Name: "receipt",
		Python: &observation{
			Status: "completed", Derived: map[string]any{}, Effects: map[string]any{},
			HomeDirtyReceiptTrace: map[string]int{"set_true": 2, "set_false": 1, "deleted": 0, "other_write": 0},
		},
		Go: &observation{
			Status: "completed", Derived: map[string]any{}, Effects: map[string]any{},
			HomeDirtyReceiptTrace: map[string]int{"set_true": 1, "set_false": 0, "deleted": 1, "other_write": 0},
		},
	}})
	if err != nil {
		t.Fatal(err)
	}
	stripReportValues(&result)
	trace := result.Cases[0].HomeDirtyReceiptTrace
	if trace["python"]["set_true"] != 2 || trace["python"]["set_false"] != 1 ||
		trace["go"]["set_true"] != 1 || trace["go"]["deleted"] != 1 {
		t.Fatalf("home receipt write trace was lost or changed: %#v", trace)
	}
	if result.Cases[0].Python != nil || result.Cases[0].Go != nil {
		t.Fatal("value-bearing observations should still be stripped")
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

func TestPairedAdmissionDetectsBYOKSplit(t *testing.T) {
	py, goRun := ruleRun(), ruleRun()
	for _, run := range []*observation{py, goRun} {
		run.Document = map[string]any{"finalization_job_id": "job"}
		run.QueueFanout = "fanout"
		run.Admitted = &admission{Job: "job", Fanout: "fanout"}
	}
	py.Admitted.OwnKey = true
	caseData := []replayCase{{Name: "byok-split", Python: py, Go: goRun}}
	result, err := compare(caseData)
	if err != nil || result.Matched != 0 || result.Unexplained != 1 ||
		!hasKindPath(result.Cases[0].Differences, "different_value", "/admitted/own_key") {
		t.Fatalf("BYOK split did not produce exactly one unexplained admission finding: %+v, %v", result, err)
	}
	goRun.Admitted.OwnKey = true
	if diffs := compareObservations(py, goRun); len(diffs) != 0 {
		t.Fatalf("matching BYOK admissions produced differences: %+v", diffs)
	}
	py.Admitted = nil
	if diffs := compareObservations(py, goRun); hasKindPath(diffs, "different_value", "/admitted/own_key") {
		t.Fatalf("absent admission incorrectly produced a BYOK split: %+v", diffs)
	}
}

func TestOneSidedAdmissionRequiresNamedOrdinarySyncException(t *testing.T) {
	python, goRun := ruleRun(), ruleRun()
	for _, run := range []*observation{python, goRun} {
		run.Document = map[string]any{"finalization_job_id": "job", "fanout_key": "key"}
	}
	python.Admitted = &admission{Job: "job", Fanout: "key"}
	python.QueueFanout = "key"
	if diffs := compareObservations(python, goRun); len(diffs) != 1 ||
		diffs[0] != (difference{Path: "/admitted", Kind: "missing_in_go"}) {
		t.Fatalf("identical documents hid a missing Go admission: %+v", diffs)
	}

	python.Admitted, goRun.Admitted = nil, &admission{Job: "job", Fanout: "key", Engine: "go"}
	python.Document = map[string]any{}
	goRun.QueueFanout = "key"
	goRun.OrdinarySyncDiagnostic = true
	if diffs := compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/admitted") {
		t.Fatalf("Go admission alone suppressed the missing Python admission: %+v", diffs)
	}
	python.OrdinarySyncDiagnostic = true
	if diffs := compareObservations(python, goRun); !hasExactPathReason(diffs, "/admitted", "ordinary_sync_python_callback_without_admission") {
		t.Fatalf("ordinary-sync absence did not have its named reason: %+v", diffs)
	}
	python.Admitted, goRun.Admitted = goRun.Admitted, nil
	if diffs := compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/admitted") {
		t.Fatalf("ordinary-sync mode suppressed the missing Go admission: %+v", diffs)
	}
}

func TestQueueFanoutEvidenceRequiresAdmission(t *testing.T) {
	python, goRun := ruleRun(), ruleRun()
	goRun.QueueFanout = "orphaned-key"
	if diffs := compareObservations(python, goRun); !hasKindPath(diffs, "invalid_binding", "/go/admitted") {
		t.Fatalf("orphaned Go queue evidence was hidden: %+v", diffs)
	}
}

func TestUnboundGoFanoutKeyRemainsUnexplained(t *testing.T) {
	python, goRun := ruleRun(), ruleRun()
	python.Document = map[string]any{}
	goRun.Document = map[string]any{"fanout_key": "unbound"}
	diffs := compareObservations(python, goRun)
	want := difference{Path: "/conversation/fanout_key", Kind: "missing_in_python"}
	if len(diffs) != 1 || diffs[0] != want {
		t.Fatalf("unbound Go fanout key must produce an unexplained difference: %+v", diffs)
	}
	goRun.Admitted = &admission{Job: "go-job", Fanout: "unbound"}
	mustMap(goRun.Document)["finalization_job_id"] = "go-job"
	goRun.QueueFanout = "other-key"
	if diffs := compareObservations(python, goRun); !hasUnexplainedAt(diffs, want.Path) {
		t.Fatalf("matching admission and stored keys without a queue binding hid the fanout key: %+v", diffs)
	}
}

func TestAdmissionIDsAreValidatedPerSideWithoutCrossEngineComparison(t *testing.T) {
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
	finalizationJobUnexplained := false
	for _, diff := range diffs {
		if diff.Path == "/conversation/finalization_job_id" {
			if diff.Reason != "" {
				t.Fatalf("finalization_job_id remains a go_gap pending the status-route fix: %v", diff)
			}
			finalizationJobUnexplained = true
			continue
		}
		if diff.Reason == "" {
			t.Fatalf("verified binding and timestamp drift: %v", diff)
		}
	}
	if !finalizationJobUnexplained {
		t.Fatalf("expected the Go job pointer difference to remain visible: %+v", diffs)
	}
	for _, diff := range diffs {
		if diff.Path == "/conversation/fanout_key" || diff.Path == "/fanout_key" || strings.HasPrefix(diff.Path, "/admitted") {
			t.Fatalf("cross-engine admission identifiers were compared: %+v", diff)
		}
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

func TestCompareKeepsBooleanAndIntegerValuesDistinct(t *testing.T) {
	t.Parallel()
	var diffs []difference
	compareValue(&diffs, "/conversation/enabled", true, json.Number("1"))
	if len(diffs) != 1 || diffs[0].Kind != "different_value" || diffs[0].Reason != "" {
		t.Fatalf("boolean-to-integer change was normalized away: %+v", diffs)
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
