package main

import (
	"encoding/json"
	"fmt"
	"slices"
	"strconv"
	"strings"
	"time"
)

func compareObservations(python, goRun *observation) []difference {
	diffs := []difference{}
	compareValue(&diffs, "/status", python.Status, goRun.Status)
	compareValue(&diffs, "/conversation", python.Document, goConversation(goRun, python))
	compareFanout(&diffs, python, goRun)
	if python.Home != nil || goRun.Home != nil {
		compareObject(&diffs, "/home", python.Home, goRun.Home)
	}
	compareObject(&diffs, "/derived_documents", python.Derived, goRun.Derived)
	compareObject(&diffs, "/effects", python.Effects, goRun.Effects)
	if !slices.Equal(python.NotesPromptHashes, goRun.NotesPromptHashes) {
		addDifference(&diffs, "/notes_prompt_sha256", "different_value")
	}
	compareObject(&diffs, "/provider_calls", countProviderCalls(python.ProviderCalls), countProviderCalls(goRun.ProviderCalls))
	compareObject(&diffs, "/webhooks", webhookGroups(python), webhookGroups(goRun))
	for i := range diffs {
		diff := &diffs[i]
		switch diff.Kind {
		case "different_value":
			if diff.Reason == "" {
				diff.Reason = allowedDifference(diff.Path, python, goRun)
			}
		case "missing_in_go":
			if unported(diff.Path) {
				diff.Kind = "unported"
			}
		}
	}
	validateBinding(&diffs, "/python", python, false)
	validateBinding(&diffs, "/go", goRun, true)
	if (python.Admitted == nil) != (goRun.Admitted == nil) {
		addDifference(&diffs, "/admitted", "different_value")
	} else if python.Admitted != nil {
		compareValue(&diffs, "/admitted/own_key", python.Admitted.OwnKey, goRun.Admitted.OwnKey)
	}
	return diffs
}

// The Python conversation has no fanout key field. Its queue document owns that
// binding. Compare Go's stored conversation key to the Python queue key separately.
func goConversation(goRun, python *observation) any {
	doc, ok := goRun.Document.(map[string]any)
	if !ok || python.QueueFanout == "" || documentField(python, "fanout_key") != nil {
		return goRun.Document
	}
	fields := make(map[string]any, len(doc))
	for name, value := range doc {
		if name != "fanout_key" {
			fields[name] = value
		}
	}
	return fields
}

func compareFanout(diffs *[]difference, python, goRun *observation) {
	if python.Admitted == nil || goRun.Admitted == nil {
		return
	}
	path := "/fanout_key"
	actual, ok := documentField(goRun, "fanout_key").(string)
	if !ok || actual == "" {
		addDifference(diffs, path, "missing_in_go")
		return
	}
	if python.QueueFanout == "" || python.QueueFanout != python.Admitted.Fanout ||
		actual != goRun.Admitted.Fanout || actual != goRun.QueueFanout {
		addDifference(diffs, path, "invalid_binding")
	} else if python.QueueFanout != actual {
		*diffs = append(*diffs, difference{
			Path: path, Kind: "different_value",
			Reason: "Python job and Go conversation fanout keys independently match their admitted bindings",
		})
	}
}

func countProviderCalls(calls []string) map[string]any {
	counts := make(map[string]int)
	for _, lane := range calls {
		counts[lane]++
	}
	fields := make(map[string]any, len(counts))
	for lane, count := range counts {
		fields[lane] = json.Number(strconv.Itoa(count))
	}
	return fields
}

func documentField(run *observation, field string) any {
	return objectField(run.Document, field)
}

func objectField(value any, field string) any {
	doc, ok := value.(map[string]any)
	if !ok {
		return nil
	}
	return doc[field]
}

func timestampInWindow(run *observation) bool {
	stamp, ok := objectField(documentField(run, "updated_at"), "$timestamp").(string)
	if !ok {
		return false
	}
	t, err := time.Parse(time.RFC3339Nano, stamp)
	return err == nil && run.UpdatedAtChanged && !run.Started.IsZero() && !run.Finished.Before(run.Started) &&
		!t.Before(run.Started) && !t.After(run.Finished)
}

func validateBinding(diffs *[]difference, side string, run *observation, goSide bool) {
	if run.UpdatedAtChanged && run.Document != nil && !timestampInWindow(run) {
		addDifference(diffs, side+"/conversation/updated_at", "invalid_clock")
	}
	if run.Admitted == nil {
		return
	}
	ids := run.Admitted
	if ids.Job == "" || ids.Fanout == "" || run.QueueFanout != ids.Fanout {
		addDifference(diffs, side+"/admitted", "invalid_binding")
	}
	if run.Document != nil && documentField(run, "finalization_job_id") != ids.Job {
		addDifference(diffs, side+"/conversation/finalization_job_id", "invalid_binding")
	}
	if actual := documentField(run, "fanout_key"); (actual != nil || goSide && len(run.Webhooks) > 0) && actual != ids.Fanout {
		addDifference(diffs, side+"/conversation/fanout_key", "invalid_binding")
	}
	for i, value := range run.Webhooks {
		if objectField(value, "app") != "developer-created" && objectField(value, "idempotency_key") != ids.Fanout {
			addDifference(diffs, fmt.Sprintf("%s/webhooks/%d/idempotency_key", side, i), "invalid_binding")
		}
	}
}

func allowedDifference(path string, python, goRun *observation) string {
	if path == "/conversation/finalization_job_id" && python.Admitted != nil && goRun.Admitted != nil &&
		python.Admitted.Job != "" && goRun.Admitted.Job != "" &&
		documentField(python, "finalization_job_id") == python.Admitted.Job &&
		documentField(goRun, "finalization_job_id") == goRun.Admitted.Job {
		return "both stored identifiers bind to their own admitted queue job"
	}
	if webhookMatches(path, python) && webhookMatches(path, goRun) {
		return "both webhook keys bind to their own admitted fanout"
	}
	return ""
}

func webhookGroups(run *observation) map[string]any {
	groups := make(map[string][]any)
	for _, webhook := range run.Webhooks {
		app, ok := objectField(webhook, "app").(string)
		if !ok || app == "" {
			app = "unknown"
		}
		groups[app] = append(groups[app], webhook)
	}
	out := make(map[string]any, len(groups))
	for app, deliveries := range groups {
		out[app] = deliveries
	}
	return out
}

func webhookMatches(path string, run *observation) bool {
	suffix, ok := strings.CutPrefix(path, "/webhooks/")
	app, rest, appFound := strings.Cut(suffix, "/")
	indexText, field, indexFound := strings.Cut(rest, "/")
	index, err := strconv.ParseUint(indexText, 10, 32)
	if !ok || !appFound || !indexFound || field != "idempotency_key" || err != nil ||
		run.Admitted == nil || run.Admitted.Fanout == "" || app == "developer-created" {
		return false
	}
	deliveries, ok := webhookGroups(run)[app].([]any)
	return ok && index < uint64(len(deliveries)) &&
		objectField(deliveries[index], "idempotency_key") == run.Admitted.Fanout
}

func unported(path string) bool {
	if path == "/conversation/apps_results" || path == "/conversation/folder_id" || path == "/webhooks/developer-created" || path == "/effects/other_vectors" || path == "/effects/python_vector_payload" {
		return true
	}
	for _, collection := range []string{"folders", "memory_items", "memory_evidence", "memory_commits", "memory_operations",
		"memory_outbox", "memory_source_replacements", "memory_state", "action_items", "goals"} {
		if strings.HasPrefix(path, "/derived_documents/users~1") && strings.Contains(path, "~1"+collection+"~1") {
			return true
		}
	}
	return false
}

// approvedIdentityDifference limits the binding proofs to the sixteen paths
// approved by the pipeline lead for the pinned capture-end corpus (SCA-3551).
func approvedIdentityDifference(name, path string) bool {
	switch path {
	case "/conversation/finalization_job_id":
		switch name {
		case "kept-with-effects", "word-floor", "unicode-transcript", "compressed-standard",
			"enhanced-compressed", "own-key-resume", "last-attempt-webhook":
			return true
		}
	case "/fanout_key":
		switch name {
		case "kept-with-effects", "unicode-transcript", "compressed-standard",
			"enhanced-compressed", "own-key-resume", "last-attempt-webhook":
			return true
		}
	case "/webhooks/audit/0/idempotency_key", "/webhooks/fixture/0/idempotency_key":
		return name == "kept-with-effects"
	case "/webhooks/unavailable-fixture/0/idempotency_key":
		return name == "last-attempt-webhook"
	}
	return false
}
