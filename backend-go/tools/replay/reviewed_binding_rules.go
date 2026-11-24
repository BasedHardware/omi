package main

import "strings"

var reviewedGoOnlyFields = []string{
	"finalization_engine", "finalization_owner_epoch", "finalization_revision",
	"go_sync_minimum_discarded", "go_sync_minimum_revision",
}

func validateReviewedGoOnlyFields(diffs *[]difference, python, goRun *observation) {
	if python == nil || goRun == nil {
		return
	}
	if hasReviewedGoOnlyFields(goRun) {
		for _, field := range reviewedGoOnlyFields {
			if hasDocumentField(python.Document, field) {
				addDifference(diffs, "/python/conversation/"+field, "invalid_binding")
			}
		}
	}
	if goRun.Admitted != nil && python.Admitted == nil {
		for _, field := range []string{"finalization_job_id", "fanout_key"} {
			if hasDocumentField(python.Document, field) {
				addDifference(diffs, "/python/conversation/"+field, "invalid_binding")
			}
		}
	}
}

func hasReviewedGoOnlyFields(run *observation) bool {
	if run == nil {
		return false
	}
	for _, field := range reviewedGoOnlyFields {
		if hasDocumentField(run.Document, field) {
			return true
		}
	}
	return false
}

func hasDocumentField(value any, field string) bool {
	doc, ok := value.(map[string]any)
	if !ok {
		return false
	}
	_, exists := doc[field]
	return exists
}

func validateGoFenceBinding(diffs *[]difference, side string, run *observation) {
	if run == nil || (!hasFenceField(run) && (run.Admitted == nil || run.Admitted.Engine != "go")) {
		return
	}
	if hasFenceField(run) && !goFenceBinds(run) {
		addDifference(diffs, side+"/conversation/finalization_engine", "invalid_binding")
	}
	for _, field := range []string{"finalization_engine", "finalization_owner_epoch", "finalization_revision"} {
		if !hasDocumentField(run.Document, field) {
			addDifference(diffs, side+"/conversation/"+field, "invalid_binding")
		}
	}
}

func hasFenceField(run *observation) bool {
	return hasDocumentField(run.Document, "finalization_engine") ||
		hasDocumentField(run.Document, "finalization_owner_epoch") ||
		hasDocumentField(run.Document, "finalization_revision")
}

func goFenceBinds(run *observation) bool {
	if run == nil || run.Admitted == nil || run.Admitted.Engine != "go" {
		return false
	}
	epoch, epochOK := integerValue(documentField(run, "finalization_owner_epoch"))
	revision, revisionOK := integerValue(documentField(run, "finalization_revision"))
	return documentField(run, "finalization_engine") == "go" && epochOK && epoch > 0 && epoch == run.Admitted.OwnerEpoch &&
		revisionOK && revision > 0 && revision == run.Admitted.Revision && documentField(run, "finalization_job_id") == run.Admitted.Job
}

func validateGoMinimumBinding(diffs *[]difference, side string, run *observation) {
	if run == nil || (!hasDocumentField(run.Document, "go_sync_minimum_discarded") && !hasDocumentField(run.Document, "go_sync_minimum_revision")) {
		return
	}
	if !goMinimumBinds(run) {
		addDifference(diffs, side+"/conversation/go_sync_minimum_revision", "invalid_binding")
	}
}

func goMinimumBinds(run *observation) bool {
	if run == nil || run.Admitted == nil {
		return false
	}
	discarded, discardedOK := documentField(run, "go_sync_minimum_discarded").(bool)
	revision, revisionOK := integerValue(documentField(run, "go_sync_minimum_revision"))
	syncRevision, syncRevisionOK := integerValue(documentField(run, "sync_content_revision"))
	return discardedOK && revisionOK && revision > 0 && syncRevisionOK && revision == syncRevision &&
		discarded == (documentField(run, "discarded") == true)
}

func approvedGoOnlyDifference(path string, python, goRun *observation) string {
	if python == nil || goRun == nil {
		return ""
	}
	if field, ok := strings.CutPrefix(path, "/conversation/"); ok {
		switch field {
		case "finalization_engine", "finalization_owner_epoch", "finalization_revision":
			if hasFenceField(goRun) && goFenceBinds(goRun) && !hasDocumentField(python.Document, field) {
				return "Go ownership fence fields bind to its admitted job; the Python row carries no Go fence metadata"
			}
		case "fanout_key":
			if goAdmissionBinds(goRun) && !hasDocumentField(python.Document, field) {
				return "Go fanout key binds to its admitted queue job; the Python row carries no Go fanout key"
			}
			if admissionBinds(python) && goAdmissionBinds(goRun) {
				return "Python and Go fanout keys each bind to their own admitted queue job"
			}
		case "go_sync_minimum_discarded", "go_sync_minimum_revision":
			if goMinimumBinds(goRun) && !hasDocumentField(python.Document, field) {
				return "Go deterministic-minimum receipt binds to its own sync content revision and discarded outcome; the Python row carries no Go receipt"
			}
		}
	}
	if path == "/admitted" || path == "/admitted/job_id" || path == "/admitted/fanout_key" {
		if python.Admitted == nil && goAdmissionBinds(goRun) {
			return "Go job and fanout IDs bind to its admitted queue job; the Python row has no Go admission"
		}
		if admissionBinds(python) && goAdmissionBinds(goRun) {
			return "Python and Go job and fanout IDs each bind to their own admitted queue job"
		}
	}
	return ""
}

func goAdmissionBinds(run *observation) bool {
	if run == nil || run.Admitted == nil || run.Admitted.Job == "" || run.Admitted.Fanout == "" || run.QueueFanout != run.Admitted.Fanout {
		return false
	}
	return documentField(run, "finalization_job_id") == run.Admitted.Job && documentField(run, "fanout_key") == run.Admitted.Fanout
}

func admissionBinds(run *observation) bool {
	if run == nil || run.Admitted == nil || run.Admitted.Job == "" || run.Admitted.Fanout == "" || run.QueueFanout != run.Admitted.Fanout {
		return false
	}
	return documentField(run, "finalization_job_id") == run.Admitted.Job
}
