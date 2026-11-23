package main

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

func compareObservations(python, goRun *observation) []difference {
	return compareObservationsForRun(
		python,
		goRun,
		generatedHomeTokenCounts([]replayCase{{Python: python}}, false),
		generatedHomeTokenCounts([]replayCase{{Go: goRun}}, true),
	)
}

func compareObservationsForRun(python, goRun *observation, pythonTokens, goTokens map[string]int) []difference {
	diffs := []difference{}
	compareValue(&diffs, "/status", python.Status, goRun.Status)
	compareValue(&diffs, "/conversation", python.Document, goConversation(goRun, python))
	compareDerivedDocuments(&diffs, python, goRun)
	compareObject(&diffs, "/effects", python.Effects, goRun.Effects)
	compareObject(&diffs, "/provider_calls", countProviderCalls(python.ProviderCalls), countProviderCalls(goRun.ProviderCalls))
	compareObject(&diffs, "/webhooks", webhookGroups(python), webhookGroups(goRun))
	for i := range diffs {
		diff := &diffs[i]
		switch diff.Kind {
		case "different_value":
			if diff.Reason == "" {
				diff.Reason = approvedTimestampDifference(diff.Path, python, goRun)
			}
			if diff.Reason == "" {
				var failureReason string
				diff.Reason, failureReason = protectedDifferenceEvidence(diff.Path, python, goRun)
				if diff.Reason == "" && diff.FailureReason == "" {
					diff.FailureReason = failureReason
				}
			}
			if diff.Reason == "" {
				diff.Reason = approvedEpisodeAttachMemoDifference(diff.Path, python, goRun)
			}
			if diff.Reason == "" {
				diff.Reason = allowedHomeTokenDifference(diff.Path, python, goRun, pythonTokens, goTokens)
			}
			if diff.Reason == "" {
				diff.Reason = approvedGoOnlyDifference(diff.Path, python, goRun)
			}
			if diff.Reason == "" {
				diff.Reason = approvedBatchPrivacyDifference(diff.Path, python, goRun)
			}
			if diff.Reason == "" && webhookMatches(diff.Path, python) && webhookMatches(diff.Path, goRun) {
				diff.Reason = "both webhook keys bind to their own admitted fanout"
			}
		case "missing_in_go":
			if diff.Reason == "" {
				var failureReason string
				diff.Reason, failureReason = protectedDifferenceEvidence(diff.Path, python, goRun)
				if diff.Reason == "" && diff.FailureReason == "" {
					diff.FailureReason = failureReason
				}
			}
			if diff.Reason == "" && unported(diff.Path) {
				diff.Kind = "unported"
			}
		case "missing_in_python":
			var failureReason string
			diff.Reason, failureReason = protectedDifferenceEvidence(diff.Path, python, goRun)
			if diff.Reason == "" && diff.FailureReason == "" {
				diff.FailureReason = failureReason
			}
			if diff.Reason == "" {
				diff.Reason = approvedGoOnlyDifference(diff.Path, python, goRun)
			}
		}
	}
	validateTimestampEvidence(&diffs, "python", python)
	validateTimestampEvidence(&diffs, "go", goRun)
	validateBatchPrivacyEvidence(&diffs, "python", python)
	validateBatchPrivacyEvidence(&diffs, "go", goRun)
	validateBatchPrivacyPair(&diffs, python, goRun)
	validateHomeTokenEvidence(&diffs, "python", python, pythonTokens)
	validateHomeTokenEvidence(&diffs, "go", goRun, goTokens)
	validateBinding(&diffs, "/python", python, false)
	validateBinding(&diffs, "/go", goRun, true)
	validateReviewedGoOnlyFields(&diffs, python, goRun)
	return diffs
}

// Fanout IDs are validated against each side's own queue/job binding, not across engines.
func goConversation(goRun, _ *observation) any {
	doc, ok := goRun.Document.(map[string]any)
	if !ok {
		return goRun.Document
	}
	fields := make(map[string]any, len(doc))
	for name, value := range doc {
		if name == "fanout_key" {
			continue
		}
		fields[name] = value
	}
	return fields
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
	return run.UpdatedAtChanged && validTimestampValue(run, documentField(run, "updated_at"), true)
}

func validateBinding(diffs *[]difference, side string, run *observation, goSide bool) {
	if run == nil {
		return
	}
	if goSide {
		validateGoFenceBinding(diffs, side, run)
		validateGoMinimumBinding(diffs, side, run)
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
