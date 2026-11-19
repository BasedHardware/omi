package main

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

func compareObservations(python, goRun *observation) []difference {
	diffs := []difference{}
	compareValue(&diffs, "/status", python.Status, goRun.Status)
	compareValue(&diffs, "/conversation", python.Document, goRun.Document)
	compareObject(&diffs, "/derived_documents", python.Derived, goRun.Derived)
	compareObject(&diffs, "/effects", python.Effects, goRun.Effects)
	compareObject(&diffs, "/webhooks", webhookGroups(python), webhookGroups(goRun))
	for i := range diffs {
		diff := &diffs[i]
		switch diff.Kind {
		case "different_value":
			diff.Reason = allowedDifference(diff.Path, python, goRun)
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
	switch path {
	case "/conversation/updated_at/$timestamp":
		if timestampInWindow(python) && timestampInWindow(goRun) {
			return "both writes occurred within their observed replay windows"
		}
	case "/conversation/fanout_key":
		if python.Admitted != nil && goRun.Admitted != nil && python.Admitted.Fanout != "" && goRun.Admitted.Fanout != "" &&
			documentField(python, "fanout_key") == python.Admitted.Fanout &&
			documentField(goRun, "fanout_key") == goRun.Admitted.Fanout {
			return "both stored fanout identifiers bind to their own admitted job"
		}
	case "/conversation/finalization_job_id":
		if python.Admitted != nil && goRun.Admitted != nil && python.Admitted.Job != "" && goRun.Admitted.Job != "" &&
			documentField(python, "finalization_job_id") == python.Admitted.Job &&
			documentField(goRun, "finalization_job_id") == goRun.Admitted.Job {
			return "both stored identifiers bind to their own admitted queue job"
		}
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
	if path == "/conversation/apps_results" || path == "/conversation/folder_id" || path == "/webhooks/developer-created" || path == "/effects/other_vectors" {
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
