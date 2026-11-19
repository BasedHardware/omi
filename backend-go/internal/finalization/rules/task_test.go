package rules

import (
	"strings"
	"testing"
)

func TestF05OrdinaryTasksRequireAnOpaqueJobAndPositiveGeneration(t *testing.T) {
	t.Parallel()
	cases := map[string]TaskKind{
		`{"job_id":"job","dispatch_generation":1}`:                              TaskOrdinary,
		`{"job_id":"merge-job","dispatch_generation":1}`:                        TaskMerge,
		`{"job_id":"quiet-job","dispatch_generation":1}`:                        TaskQuiet,
		`{"job_id":"job","dispatch_generation":true}`:                           TaskInvalid,
		`{"job_id":"job","dispatch_generation":0}`:                              TaskInvalid,
		`{"job_id":"job","dispatch_generation":1.0}`:                            TaskInvalid,
		`{"job_id":"job","dispatch_generation":1,"key":"extra"}`:                TaskInvalid,
		`{"job_id":"","dispatch_generation":1}`:                                 TaskInvalid,
		`{"job_id":"` + strings.Repeat("é", 129) + `","dispatch_generation":1}`: TaskInvalid,
	}
	for body, want := range cases {
		if got := DecodeTask([]byte(body)); got.Kind != want {
			t.Errorf("%s: got %v, want %v", body, got.Kind, want)
		}
	}
}

func TestF34EnrichmentIsASeparateEnvelope(t *testing.T) {
	t.Parallel()
	key, token := strings.Repeat("a", 64), strings.Repeat("b", 32)
	input := `{"kind":"sync_reprocess","key":"` + key + `","task_token":"` + token + `"}`
	if got := DecodeTask([]byte(input)); got != (Task{Kind: TaskEnrichment, Key: key, Token: token}) {
		t.Fatalf("valid enrichment: %+v", got)
	}
	for _, invalid := range []string{
		input[:len(input)-1] + `,"job_id":"job","dispatch_generation":1}`,
		strings.Replace(input, token, "invalid", 1),
	} {
		if got := DecodeTask([]byte(invalid)); got.Kind != TaskInvalidEnrichment {
			t.Errorf("invalid enrichment routed: %+v", got)
		}
	}
}
