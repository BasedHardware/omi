package conversations

import (
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
)

func TestBoundCompletedMinimumMustStillOweNotes(t *testing.T) {
	t.Parallel()
	row := map[string]any{
		"status":                   "completed",
		"finalization_job_id":      "current-job",
		"summary_title_provenance": "server_minimum",
	}
	structured := map[string]any{"title": "Recorded capture", "title_provenance": "server_minimum"}
	if !finalizerMinimum(row, structured, nil) {
		t.Fatal("the bound finalizer skipped an unfinished server minimum")
	}
	if finalizerMinimum(row, structured, []finalization.NoteSection{{Heading: "Recap", Body: "Existing summary"}}) {
		t.Fatal("a stored summary reopened notes debt")
	}
	row["relevance_decision"] = map[string]any{"verdict": "keep", "decided_by": "rule", "reason": "content_below_floor"}
	if finalizerMinimum(row, structured, nil) {
		t.Fatal("an intentional short-clip minimum reopened notes debt")
	}
	delete(row, "relevance_decision")
	delete(row, "finalization_job_id")
	if finalizerMinimum(row, structured, nil) {
		t.Fatal("a worker took unbound notes debt")
	}
}
