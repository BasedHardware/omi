package main

import (
	"reflect"
	"strings"
)

const unreadableReplayCase = "unreadable-ciphertext-dead-letters"

func markUnreadableTerminalConsequences(entry *caseReport, python, goRun *observation) {
	if entry.Name != unreadableReplayCase || python.Status != "parked" || goRun.Status != "failure" ||
		len(python.ProviderCalls) != 0 || len(goRun.ProviderCalls) != 0 {
		return
	}
	job, _ := goRun.GoEvidence["job"].(map[string]any)
	const cause = "conversation_unreadable"
	ciphertext := documentField(python, "transcript_segments")
	if job["state"] != "dead_letter" || job["cause"] != cause ||
		documentField(goRun, "finalization_status") != "dead_letter" ||
		ciphertext == nil || ciphertext == "" || !reflect.DeepEqual(ciphertext, documentField(goRun, "transcript_segments")) {
		return
	}
	terminalPaths := map[string]string{
		"/conversation/finalization_status": "missing_in_python",
		"/go/admitted":                      "invalid_binding",
	}
	for path, value := range python.Derived {
		row, _ := value.(map[string]any)
		if strings.HasPrefix(path, "sync_reprocess_outbox/") && row["uid"] == goRun.OwnerID &&
			row["conversation_id"] == goRun.ConversationID && row["age_gate_parked"] == true {
			terminalPaths["/derived_documents/"+escapePointer(path)] = "missing_in_go"
		}
	}
	attention := "users/" + goRun.OwnerID + "/processing_attention_items/conv-summary:" + goRun.ConversationID + ":"
	for path, value := range goRun.Derived {
		row, _ := value.(map[string]any)
		if strings.HasPrefix(path, attention) && row["failure_code"] == cause {
			terminalPaths["/derived_documents/"+escapePointer(path)] = "missing_in_python"
		}
	}
	privacy, operations := python.BatchPrivacy, python.Cost.Firestore
	if privacy != nil && !privacy.Seed.Exists && !privacy.Final.Exists && privacyStateMatchesSeed(python) &&
		python.PythonRetry != nil && operations.BatchPrivacyDocumentReads == python.PythonRetry.CallbackPending &&
		operations.BatchPrivacyDocumentWrites == 0 && operations.BatchPrivacyDocumentDeletes == 0 {
		privacyPath := "/python/derived_documents/" + escapePointer(batchPrivacyDocumentPath(python.OwnerID))
		terminalPaths["/python/batch_pipeline_privacy/final"] = "missing_document"
		terminalPaths["/python/batch_pipeline_privacy/final_snapshot"] = "invalid_binding"
		terminalPaths["/python/firestore_operations/batch_pipeline_privacy_document"] = "invalid_operations"
		terminalPaths[privacyPath+"/memo_schema"] = "missing_evidence"
		terminalPaths[privacyPath+"/memo_token"] = "invalid_binding"
	}
	for i := range entry.Differences {
		diff := &entry.Differences[i]
		diff.UnreadableTerminalConsequence = terminalPaths[diff.Path] == diff.Kind
	}
}
