package main

import (
	"encoding/json"
	"fmt"
	"maps"
	"strconv"
	"strings"
)

func compareObservations(python, goRun *observation) []difference {
	diffs, _ := compareObservationsForRun(
		python,
		goRun,
		generatedHomeTokenCounts([]replayCase{{Python: python}}, false),
		generatedHomeTokenCounts([]replayCase{{Go: goRun}}, true),
	)
	return diffs
}

func compareObservationsForRun(python, goRun *observation, pythonTokens, goTokens map[string]int) ([]difference, map[string]attachMemoCheck) {
	diffs := []difference{}
	terminalChecks := terminalMemoChecks(python, goRun)
	compareValue(&diffs, "/status", python.Status, goRun.Status)
	compareAdmissions(&diffs, python, goRun)
	compareValue(&diffs, "/conversation", python.Document, goConversation(goRun))
	compareDerivedDocuments(&diffs, python, goRun)
	if terminalChecks != nil {
		filtered := diffs[:0]
		for _, diff := range diffs {
			if episodeAttachMemoField(diff.Path, python) && episodeAttachMemoField(diff.Path, goRun) {
				continue
			}
			filtered = append(filtered, diff)
		}
		diffs = filtered
	}
	if terminalChecks == nil {
		validateGoAttachMemoEvidence(&diffs, goRun)
	}
	compareObject(&diffs, "/effects", python.Effects, goRun.Effects)
	compareObject(&diffs, "/provider_calls", countProviderCalls(python.ProviderCalls), countProviderCalls(goRun.ProviderCalls))
	compareObject(&diffs, "/webhooks", webhookGroups(python), webhookGroups(goRun))
	reviewSpeakerDifferences(&diffs, python, goRun)
	reviewRuledSyncWrites(&diffs, python, goRun)
	for i := range diffs {
		diff := &diffs[i]
		if terminalChecks == nil && diff.Reason == "" {
			diff.Reason = approvedEpisodeAttachMemoDifference(diff.Path, python, goRun)
		}
		if terminalChecks == nil && diff.Reason == "" && goRun.EpisodeAttachMemoExpected && !goRun.EpisodeAttachMemoValid &&
			episodeAttachMemoField(diff.Path, goRun) {
			diff.FailureReason = "go_attach_memo_invalid"
		}
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
			if diff.Reason == "" {
				var failureReason string
				diff.Reason, failureReason = protectedDifferenceEvidence(diff.Path, python, goRun)
				if diff.Reason == "" && diff.FailureReason == "" {
					diff.FailureReason = failureReason
				}
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
	if terminalChecks == nil {
		validateEpisodeAttachMemoEvidence(&diffs, python, goRun)
	} else {
		for _, side := range []string{"python", "go"} {
			if check := terminalChecks[side]; !check.Valid {
				diffs = append(diffs, difference{Path: "/" + side + "/episode_attach_memo", Kind: "invalid_binding", FailureReason: check.FailureReason})
			}
		}
	}
	validateReviewedGoOnlyFields(&diffs, python, goRun)
	return diffs, terminalChecks
}

func ordinarySyncDiagnosticPair(python, goRun *observation) bool {
	return python.OrdinarySyncDiagnostic && goRun.OrdinarySyncDiagnostic
}

func compareAdmissions(diffs *[]difference, python, goRun *observation) {
	switch {
	case python.Admitted != nil && goRun.Admitted != nil:
		compareValue(diffs, "/admitted/own_key", python.Admitted.OwnKey, goRun.Admitted.OwnKey)
	case python.Admitted != nil:
		addDifference(diffs, "/admitted", "missing_in_go")
	case goRun.Admitted != nil:
		diff := difference{Path: "/admitted", Kind: "missing_in_python"}
		if ordinarySyncDiagnosticPair(python, goRun) && goRun.Admitted.Engine == "go" {
			diff.Reason = "ordinary_sync_python_callback_without_admission"
		}
		*diffs = append(*diffs, diff)
	}
}

func validateGoAttachMemoEvidence(diffs *[]difference, goRun *observation) {
	if goRun == nil || goRun.EpisodeAttachMemoValid {
		return
	}
	conversation, conversationOK := goRun.Document.(map[string]any)
	needsMemo := conversationOK && hasDocumentField(conversation, "episode_id") &&
		conversation["transcript_segments"] != nil
	linkPath := "users/" + goRun.OwnerID + "/episode_links/" + goRun.ConversationID
	link := goRun.Derived[linkPath]
	var hasMemo, hasLiveMemo bool
	for _, field := range []string{"attach_revision", "attach_completed", "attach_finalized", "attach_owner_id"} {
		hasMemo = hasMemo || hasDocumentField(link, field)
		hasLiveMemo = hasLiveMemo || objectField(link, field) != nil
	}
	if !hasLiveMemo {
		switch goRun.EpisodeAttachMemoFailureReason {
		case "missing_transcript", "transcript_decode_failed", "discarded_without_memo", "content_key_unavailable":
			// An unkeyable row may omit its memo. A stored memo still needs proof.
			return
		}
	}
	if !hasMemo && !needsMemo {
		return
	}
	for _, diff := range *diffs {
		if episodeAttachMemoField(diff.Path, goRun) {
			return
		}
	}
	path := "/go/derived_documents/" + escapePointer(linkPath) + "/attach_memo_evidence"
	*diffs = append(*diffs, difference{
		Path: path, Kind: "invalid_binding", FailureReason: goRun.EpisodeAttachMemoFailureReason,
	})
}

// A bound Go fanout key is validated against its own queue and job.
func goConversation(goRun *observation) any {
	doc, ok := goRun.Document.(map[string]any)
	if !ok || !goAdmissionBinds(goRun) {
		return goRun.Document
	}
	fields := maps.Clone(doc)
	delete(fields, "fanout_key")
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
	return run.UpdatedAtChanged && validTimestampValue(run, documentField(run, "updated_at"))
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
		if run.QueueFanout != "" {
			addDifference(diffs, side+"/admitted", "invalid_binding")
		}
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
