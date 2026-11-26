package main

import (
	"encoding/json"
	"maps"
	"strings"
	"testing"
	"time"
)

func pairedErasureRuns(t *testing.T) (*observation, *observation, string) {
	t.Helper()
	const fixture = "erase-removes-owner-and-jobs"
	const owner = "replay-" + fixture
	path := batchPrivacyDocumentPath(owner)
	py, goRun := captureRun(t, "0.2", 1), captureRun(t, "0.2", 2)
	speakerPath := "users/" + owner + "/conversations/" + fixture + "/speaker_evidence/current"
	for i, run := range []*observation{py, goRun} {
		exit := run.SpeakerTrace.Exits[0]
		exit["uid"], exit["conversation"] = owner, fixture
		diag := mustMap(documentField(run, "owner_recognition_diagnostics"))
		diag["first_resolver"], diag["current_resolver"] = exit, exit
		mustMap(run.Document)["structured"] = map[string]any{"title": "Captured title"}
		mustMap(documentField(run, "speaker_resolution"))["assignments"] = []any{"capture"}
		setEvidence(t, run, owner, "capture", byte(i+1))
		memo := batchPrivacyRun([]string{pyMemoToken, goMemoToken}[i])
		run.OwnerID, run.ConversationID = owner, fixture
		run.SeededTokenHashes = memo.SeededTokenHashes
		run.BeforeErasure = &beforeErasure{
			Document: run.Document,
			Derived: map[string]any{
				path:        maps.Clone(memo.BatchPrivacy.Final.Fields),
				speakerPath: run.Derived[speakerDoc],
			},
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
	goRun.SpeakerTrace.Exits[0]["elapsed_seconds"] = json.Number("0.3")
	goRun.SpeakerTrace.ClockSeconds[1] = json.Number("10.3")
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
	speakerPath := "/derived_documents/" + escapePointer("users/"+py.OwnerID+"/conversations/"+py.ConversationID+"/speaker_evidence/current")
	for path, reason := range map[string]string{clockPath: "replay_clock", speakerPath + "/payload": "encrypted_envelope"} {
		found := false
		for _, diff := range diffs {
			found = found || diff.Path == "/before_erasure"+path && diff.Reason == reason
		}
		if !found {
			t.Fatalf("missing %s approval for %s: %+v", reason, path, diffs)
		}
	}
}

func TestPairedErasureComparesConversationFields(t *testing.T) {
	for _, test := range []struct {
		object, field string
		value         any
	}{
		{"speaker_resolution", "assignments", []any{"different speaker"}},
		{"structured", "title", "Different title"},
	} {
		t.Run(test.field, func(t *testing.T) {
			py, goRun, _ := pairedErasureRuns(t)
			mustMap(objectField(goRun.BeforeErasure.Document, test.object))[test.field] = test.value
			diffs := compareObservations(py, goRun)
			path := "/before_erasure/conversation/" + test.object + "/" + test.field
			if test.field == "assignments" {
				path += "/0"
			}
			if !hasKindPath(diffs, "different_value", path) {
				t.Fatalf("pre-wipe mutation at %s was lost: %+v", path, diffs)
			}
		})
	}
}

func TestPairedErasureComparesAuthenticatedSpeakerPayloads(t *testing.T) {
	py, goRun, _ := pairedErasureRuns(t)
	doc := "users/" + goRun.OwnerID + "/conversations/" + goRun.ConversationID + "/speaker_evidence/current"
	setEvidence(t, goRun, goRun.OwnerID, "different capture", 2)
	goRun.BeforeErasure.Derived[doc] = goRun.Derived[speakerDoc]
	delete(goRun.Derived, speakerDoc)
	diffs := compareObservations(py, goRun)
	for _, diff := range diffs {
		if diff.Path == "/before_erasure/derived_documents/"+escapePointer(doc)+"/payload" &&
			diff.Kind == "different_value" && diff.Reason == "" {
			return
		}
	}
	t.Fatalf("different authenticated speaker payloads escaped comparison: %+v", diffs)
}

func TestPairedErasureRejectsUnverifiedGoSpeakerResults(t *testing.T) {
	t.Run("resolver without trace", func(t *testing.T) {
		py, goRun, _ := pairedErasureRuns(t)
		goRun.SpeakerTrace = nil
		diffs := compareObservations(py, goRun)
		if !hasKindPath(diffs, "invalid_binding", "/before_erasure/go"+clockPath) {
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
		resolverRows := 0
		for _, diff := range diffs {
			if strings.Contains(diff.Path, resolverPath) {
				resolverRows++
				if diff.Path != "/before_erasure"+resolverPath || diff.Kind != "missing_in_go" ||
					diff.FailureReason != "speaker_resolver_unverified" {
					t.Fatalf("unexpected resolver finding: %+v", diff)
				}
			}
		}
		if resolverRows != 1 {
			t.Fatalf("expected one missing resolver finding, got %+v", diffs)
		}
	})
	t.Run("invalid stored envelope", func(t *testing.T) {
		py, goRun, _ := pairedErasureRuns(t)
		doc := "users/" + goRun.OwnerID + "/conversations/" + goRun.ConversationID + "/speaker_evidence/current"
		goRun.BeforeErasure.Derived[doc] = map[string]any{"version": json.Number("1"), "payload": "invalid"}
		diffs := compareObservations(py, goRun)
		want := "/before_erasure/derived_documents/" + escapePointer(doc) + "/payload"
		for _, diff := range diffs {
			if diff.Path == want && diff.Kind == "different_value" && diff.FailureReason == "speaker_envelope_unverified" {
				return
			}
		}
		t.Fatalf("proved erasure excused a pre-wipe invalid Go speaker envelope: %+v", diffs)
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
			func(string) string { return "/before_erasure/python" + clockPath }, "invalid_binding"},
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

func TestGoDepartureSkipsOnlyAbsentAdmissionAndConversationBindings(t *testing.T) {
	for _, fixture := range []string{"worker-missing-row-fence", "erase-removes-owner-and-jobs"} {
		t.Run(fixture, func(t *testing.T) {
			_, run, _ := pairedErasureRuns(t)
			run.OwnerID, run.ConversationID = "replay-"+fixture, fixture
			if fixture == "worker-missing-row-fence" {
				run.Status = "fenced"
				run.GoEvidence = map[string]any{"job": map[string]any{"outcome": "fenced"}}
			}
			run.Admitted = &admission{Job: "go-job", Fanout: "job-fanout", Engine: "go"}
			run.Webhooks = []any{map[string]any{"app": "fixture", "idempotency_key": "wrong"}}
			var diffs []difference
			validateBinding(&diffs, "/go", run, true)
			if len(diffs) != 1 || !hasKindPath(diffs, "invalid_binding", "/go/webhooks/0/idempotency_key") {
				t.Fatalf("proved departure must preserve the webhook finding: %+v", diffs)
			}

			evidence := run.GoEvidence
			for _, document := range []any{map[string]any{"finalization_job_id": "go-job"}, nil} {
				run.Document = document
				if document == nil {
					run.GoEvidence = nil
				} else {
					run.GoEvidence = evidence
				}
				diffs = nil
				validateBinding(&diffs, "/go", run, true)
				for _, path := range []string{
					"/go/conversation/finalization_engine",
					"/go/conversation/finalization_owner_epoch",
					"/go/conversation/finalization_revision",
					"/go/admitted",
				} {
					if !hasKindPath(diffs, "invalid_binding", path) {
						t.Fatalf("missing %s for present or unproved row: %+v", path, diffs)
					}
				}
			}
		})
	}
}

func TestPostErasurePrivacyUsesOnlyWitnessedIdentityExceptions(t *testing.T) {
	tests := []struct {
		name            string
		mutate          func(*observation, string, string)
		pairOK, tokenOK bool
	}{
		{"matching operations", func(*observation, string, string) {}, true, true},
		{"different account epoch", func(run *observation, _, receipt string) {
			mustMap(run.Derived[receipt])["account_epoch"] = json.Number("3")
		}, false, true},
		{"different operation kind", func(run *observation, _, receipt string) {
			mustMap(run.Derived[receipt])["purge_generation"] = json.Number("1")
		}, false, true},
		{"wrong expiration", func(run *observation, _, receipt string) {
			mustMap(run.Derived[receipt])["expires_at"] = wrappedStamp(run.Finished)
		}, false, true},
		{"wrong owner digest", func(run *observation, path, receipt string) {
			run.Derived[batchPrivacyDocumentPath("other")+strings.TrimPrefix(receipt, path)] = run.Derived[receipt]
			delete(run.Derived, receipt)
		}, false, true},
		{"ambiguous duplicate", func(run *observation, path, receipt string) {
			run.Derived[path+"/account_operations/"+strings.Repeat("c", 64)] = run.Derived[receipt]
		}, false, true},
		{"unblocked privacy", func(run *observation, _, _ string) {
			run.BatchPrivacy.Final.Fields["blocked"] = false
		}, true, false},
		{"reused pre-wipe memo", func(run *observation, _, _ string) {
			run.BatchPrivacy.Final.Fields["memo_token"] = run.BeforeErasure.BatchPrivacy.Fields["memo_token"]
		}, true, false},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			python, goRun, path := pairedErasureRuns(t)
			var goReceipt string
			for i, run := range []*observation{python, goRun} {
				fields := run.BatchPrivacy.Final.Fields
				fields["generation"], fields["account_epoch"] = json.Number("1"), json.Number("2")
				fields["blocked"], fields["purging"] = true, false
				fields["memo_token"] = []string{"423e4567e89b42d3a456426614174000", "523e4567e89b42d3a456426614174000"}[i]
				run.Cost.Firestore.BatchPrivacyDocumentWrites += 2
				receipt := path + "/account_operations/" + strings.Repeat([]string{"a", "b"}[i], 64)
				run.Derived[receipt] = map[string]any{
					"account_epoch": json.Number("2"), "purge_generation": nil,
					"expires_at": wrappedStamp(run.Finished.Add(90 * 24 * time.Hour)),
				}
				goReceipt = receipt
			}
			test.mutate(goRun, path, goReceipt)

			diffs := compareObservations(python, goRun)
			paired, memoApproved, unmatched := 0, false, 0
			for _, diff := range diffs {
				if diff.Reason == "generated_identity" {
					paired++
				}
				if diff.Path == "/derived_documents/"+escapePointer(path)+"/memo_token" {
					memoApproved = diff.Reason == postErasureMemoReason
				}
				if strings.Contains(diff.Path, "~1account_operations~1") && diff.Reason == "" {
					unmatched++
				}
			}
			if (paired == 2) != test.pairOK || memoApproved != test.tokenOK || (!test.pairOK && unmatched == 0) {
				t.Fatalf("incorrect privacy exceptions: %+v", diffs)
			}
		})
	}
}
