package main

import (
	"encoding/json"
	"strings"
	"testing"
)

const (
	seedMemoToken = "123e4567e89b42d3a456426614174000"
	pyMemoToken   = "223e4567e89b42d3a456426614174000"
	goMemoToken   = "323e4567e89b42d3a456426614174000"
)

func batchPrivacyRun(token string) *observation {
	path := batchPrivacyDocumentPath("u")
	seedFields := map[string]any{
		"memo_token":    seedMemoToken,
		"memo_schema":   json.Number("1"),
		"generation":    json.Number("4"),
		"account_epoch": json.Number("7"),
		"purging":       false,
		"blocked":       false,
		"memo_blocked":  false,
	}
	finalFields := map[string]any{
		"memo_token":    token,
		"memo_schema":   json.Number("1"),
		"generation":    json.Number("4"),
		"account_epoch": json.Number("7"),
		"purging":       false,
		"blocked":       false,
		"memo_blocked":  false,
	}
	return &observation{
		OwnerID: "u", Status: "completed", Document: map[string]any{}, Derived: map[string]any{path: finalFields}, Effects: map[string]any{},
		SeededTokenHashes: []string{tokenDigest(seedMemoToken)},
		BatchPrivacy: &batchPrivacyEvidence{
			Seed:  batchPrivacySnapshot{Exists: true, Fields: seedFields},
			Final: batchPrivacySnapshot{Exists: true, Fields: finalFields},
		},
		Cost: replayCost{Measured: true, Firestore: firestoreOperations{
			BatchPrivacyDocumentWrites: 1,
		}},
	}
}

func TestBatchPrivacyMemoRuleRequiresBoundRotationAndExactOperations(t *testing.T) {
	py, goRun := batchPrivacyRun(pyMemoToken), batchPrivacyRun(goMemoToken)
	diffs := compareObservations(py, goRun)
	if hasUnexplained(diffs) || !hasReason(diffs, "memo_token") {
		t.Fatalf("valid memo rotation was not explained: %+v", diffs)
	}
	for _, diff := range diffs {
		if diff.Path == "/derived_documents/"+escapePointer(batchPrivacyDocumentPath("u"))+"/memo_token" && diff.Reason != batchPrivacyMemoRuleReason {
			t.Fatalf("memo difference used unexpected rule: %+v", diff)
		}
	}

	tests := []struct {
		name   string
		mutate func(*observation, *observation)
		path   string
	}{
		{
			name: "malformed token",
			mutate: func(py, _ *observation) {
				py.BatchPrivacy.Final.Fields["memo_token"] = "not-a-uuid"
				mustMap(py.Derived[batchPrivacyDocumentPath("u")])["memo_token"] = "not-a-uuid"
			},
			path: "/python/derived_documents/" + escapePointer(batchPrivacyDocumentPath("u")) + "/memo_token",
		},
		{
			name: "seeded token reused",
			mutate: func(py, _ *observation) {
				py.BatchPrivacy.Final.Fields["memo_token"] = seedMemoToken
				mustMap(py.Derived[batchPrivacyDocumentPath("u")])["memo_token"] = seedMemoToken
			},
			path: "/python/derived_documents/" + escapePointer(batchPrivacyDocumentPath("u")) + "/memo_token",
		},
		{
			name: "memo schema differs across sides",
			mutate: func(_, goRun *observation) {
				goRun.BatchPrivacy.Final.Fields["memo_schema"] = json.Number("2")
				mustMap(goRun.Derived[batchPrivacyDocumentPath("u")])["memo_schema"] = json.Number("2")
			},
			path: "/derived_documents/" + escapePointer(batchPrivacyDocumentPath("u")) + "/memo_schema",
		},
		{
			name: "privacy state changed from seed",
			mutate: func(py, _ *observation) {
				py.BatchPrivacy.Final.Fields["generation"] = json.Number("5")
				mustMap(py.Derived[batchPrivacyDocumentPath("u")])["generation"] = json.Number("5")
			},
			path: "/python/derived_documents/" + escapePointer(batchPrivacyDocumentPath("u")) + "/generation",
		},
		{
			name:   "extra target read",
			mutate: func(py, _ *observation) { py.Cost.Firestore.BatchPrivacyDocumentReads = 1 },
			path:   "/python/firestore_operations/batch_pipeline_privacy_document",
		},
		{
			name:   "multiple target writes",
			mutate: func(_, goRun *observation) { goRun.Cost.Firestore.BatchPrivacyDocumentWrites = 2 },
			path:   "/go/firestore_operations/batch_pipeline_privacy_document",
		},
		{
			name:   "target document delete",
			mutate: func(_, goRun *observation) { goRun.Cost.Firestore.BatchPrivacyDocumentDeletes = 1 },
			path:   "/go/firestore_operations/batch_pipeline_privacy_document",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			py, goRun := batchPrivacyRun(pyMemoToken), batchPrivacyRun(goMemoToken)
			test.mutate(py, goRun)
			diffs := compareObservations(py, goRun)
			if !hasKindPath(diffs, "invalid_binding", test.path) && !hasKindPath(diffs, "invalid_operations", test.path) {
				t.Fatalf("negative evidence did not fail the rule: %+v", diffs)
			}
			for _, diff := range diffs {
				if strings.HasSuffix(diff.Path, "/memo_token") && diff.Reason != "" {
					t.Fatalf("invalid memo evidence still excused token difference: %+v", diff)
				}
			}
		})
	}
}
