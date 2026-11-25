package main

import (
	"encoding/json"
	"maps"
	"testing"
	"time"
)

func pairedErasureRuns(t *testing.T) (*observation, *observation, string) {
	t.Helper()
	const fixture = "erase-removes-owner-and-jobs"
	const owner = "replay-" + fixture
	path := batchPrivacyDocumentPath(owner)
	py := captureRun(t, "0.2", 1)
	exit := py.SpeakerTrace.Exits[0]
	exit["uid"], exit["conversation"] = owner, fixture
	diag := mustMap(documentField(py, "owner_recognition_diagnostics"))
	diag["first_resolver"], diag["current_resolver"] = maps.Clone(exit), maps.Clone(exit)
	goRun := ruleRun()
	goRun.Document = maps.Clone(mustMap(py.Document))
	goRun.SpeakerTrace = py.SpeakerTrace
	for i, run := range []*observation{py, goRun} {
		memo := batchPrivacyRun([]string{pyMemoToken, goMemoToken}[i])
		run.OwnerID, run.ConversationID = owner, fixture
		run.SeededTokenHashes = memo.SeededTokenHashes
		run.BeforeErasure = &beforeErasure{
			Document:     run.Document,
			Derived:      map[string]any{path: maps.Clone(memo.BatchPrivacy.Final.Fields)},
			BatchPrivacy: memo.BatchPrivacy.Final,
			Cost:         memo.Cost, Finished: run.Finished.Add(-time.Second),
		}
		run.Document = nil
		run.BatchPrivacy = memo.BatchPrivacy
		run.BatchPrivacy.Final.Fields = maps.Clone(run.BeforeErasure.BatchPrivacy.Fields)
		run.Derived = map[string]any{path: run.BatchPrivacy.Final.Fields}
		run.Cost = memo.Cost
		run.Effects = map[string]any{"erasure": map[string]any{
			"user_document_absent": true, "conversation_absent": true,
			"jobs_for_uid": json.Number("0"), "tenants_for_uid": json.Number("0"),
		}}
	}
	mustMap(py.Effects["erasure"])["jobs_for_uid"] = json.Number("1")
	py.BatchPrivacy.Final.Fields["generation"] = json.Number("5")
	py.Cost.Firestore.BatchPrivacyDocumentWrites++
	goRun.GoEvidence = map[string]any{
		"erasure": goRun.Effects["erasure"],
		"job":     map[string]any{"state": "completed"},
	}
	return py, goRun, path
}

func TestPairedErasureValidatesFinalizationBeforeTheWipe(t *testing.T) {
	py, goRun, path := pairedErasureRuns(t)
	diffs := compareObservations(py, goRun)
	for _, diff := range diffs {
		if diff.Kind == "invalid_binding" || diff.Kind == "invalid_operations" || diff.Path == "/conversation" {
			t.Fatalf("valid pre-erase evidence rejected: %+v", diff)
		}
	}
	for _, path := range []string{"/derived_documents/" + escapePointer(path) + "/generation", "/effects/erasure/jobs_for_uid"} {
		if !hasKindPath(diffs, "different_value", path) {
			t.Fatalf("post-erase difference at %s disappeared: %+v", path, diffs)
		}
	}
}

func TestPairedErasureRejectsUnverifiedGoSpeakerResults(t *testing.T) {
	t.Run("resolver without trace", func(t *testing.T) {
		py, goRun, _ := pairedErasureRuns(t)
		goRun.SpeakerTrace = nil
		diffs := compareObservations(py, goRun)
		if !hasKindPath(diffs, "invalid_binding", "/go"+clockPath) {
			t.Fatalf("proved erasure excused a pre-wipe Go result without a trace: %+v", diffs)
		}
	})
	t.Run("missing resolver result", func(t *testing.T) {
		py, goRun, _ := pairedErasureRuns(t)
		doc := mustMap(goRun.BeforeErasure.Document)
		delete(doc, "speaker_resolution")
		delete(doc, "owner_recognition_diagnostics")
		goRun.SpeakerTrace = &speakerTrace{}
		diffs := compareObservations(py, goRun)
		path := "/go/before_erasure" + resolverPath + "/current_resolver"
		if !hasKindPath(diffs, "missing_in_go", path) {
			t.Fatalf("proved erasure hid the missing pre-wipe Go resolver result: %+v", diffs)
		}
	})
	t.Run("invalid stored envelope", func(t *testing.T) {
		py, goRun, _ := pairedErasureRuns(t)
		doc := "users/" + goRun.OwnerID + "/conversations/" + goRun.ConversationID + "/speaker_evidence/current"
		goRun.BeforeErasure.Derived[doc] = map[string]any{"version": json.Number("1"), "payload": "invalid"}
		diffs := compareObservations(py, goRun)
		if !hasKindPath(diffs, "invalid_binding", "/go/derived_documents/"+escapePointer(doc)+"/payload") {
			t.Fatalf("proved erasure excused a pre-wipe invalid Go speaker envelope: %+v", diffs)
		}
	})
}

func TestPairedErasureStillRejectsBadFinalizationWitnesses(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*observation, *observation, string)
		path   func(string) string
		kind   string
	}{
		{"missing phase", func(py, _ *observation, _ string) { py.BeforeErasure = nil },
			func(string) string { return "/python/before_erasure" }, "invalid_binding"},
		{"invalid phase clock", func(py, _ *observation, _ string) { py.BeforeErasure.Finished = py.Finished.Add(time.Second) },
			func(string) string { return "/python/before_erasure" }, "invalid_binding"},
		{"invalid resolver trace", func(py, _ *observation, _ string) { py.SpeakerTrace.ClockSeconds = nil },
			func(string) string { return "/python" + clockPath }, "invalid_binding"},
		{"state drift before erase", func(py, _ *observation, path string) {
			py.BeforeErasure.BatchPrivacy.Fields["generation"] = json.Number("8")
			mustMap(py.BeforeErasure.Derived[path])["generation"] = json.Number("8")
		}, func(path string) string { return "/python/derived_documents/" + escapePointer(path) + "/generation" }, "invalid_binding"},
		{"extra reads before erase", func(py, _ *observation, _ string) {
			py.BeforeErasure.Cost.Firestore.BatchPrivacyDocumentReads++
		}, func(string) string { return "/python/firestore_operations/batch_pipeline_privacy_document" }, "invalid_operations"},
		{"Go jobs still present", func(_, goRun *observation, _ string) {
			mustMap(goRun.Effects["erasure"])["jobs_for_uid"] = json.Number("1")
		}, func(string) string { return "/effects/erasure" }, "invalid_binding"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			py, goRun, path := pairedErasureRuns(t)
			test.mutate(py, goRun, path)
			diffs := compareObservations(py, goRun)
			if !hasKindPath(diffs, test.kind, test.path(path)) {
				t.Fatalf("missing finding for invalid erasure evidence: %+v", diffs)
			}
		})
	}
}
