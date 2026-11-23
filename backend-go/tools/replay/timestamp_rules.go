package main

import (
	"strings"
	"time"
)

const postFinishWriteGrace = 5 * time.Second

type timestampKind int

const firestoreTimestamp timestampKind = iota

type timestampRule struct {
	collection string
	document   string
	field      string
	kind       timestampKind
	grace      time.Duration
}

var approvedTimestampRules = []timestampRule{
	{collection: "episodes", document: "*", field: "compose_deferred_at", kind: firestoreTimestamp},
	{collection: "episodes", document: "*", field: "created_at", kind: firestoreTimestamp, grace: postFinishWriteGrace},
	{collection: "episodes", document: "*", field: "title_changed_at", kind: firestoreTimestamp},
	{collection: "goals", document: "*", field: "updated_at", kind: firestoreTimestamp},
	{collection: "goals", document: "*/goal_history/*", field: "recorded_at", kind: firestoreTimestamp},
	{collection: "llm_usage", document: "*", field: "last_updated", kind: firestoreTimestamp},
	{collection: "memory_state", document: "apply_control", field: "updated_at", kind: firestoreTimestamp},
	{collection: "memory_state", document: "head", field: "updated_at", kind: firestoreTimestamp},
	{collection: "episode_links", document: "*", field: "updated_at", kind: firestoreTimestamp, grace: postFinishWriteGrace},
	{collection: "memory_outbox", document: "*", field: "available_at", kind: firestoreTimestamp},
	{collection: "memory_commits", document: "*", field: "updated_at", kind: firestoreTimestamp},
	{collection: "memory_operations", document: "*", field: "created_at", kind: firestoreTimestamp},
	{collection: "memory_operations", document: "*", field: "updated_at", kind: firestoreTimestamp},
	{collection: "memory_items", document: "*", field: "captured_at", kind: firestoreTimestamp},
	{collection: "memory_items", document: "*", field: "expires_at", kind: firestoreTimestamp},
	{collection: "memory_items", document: "*", field: "updated_at", kind: firestoreTimestamp},
	{collection: "memory_items", document: "*", field: "valid_from", kind: firestoreTimestamp},
	{collection: "memory_source_replacements", document: "*", field: "committed_at", kind: firestoreTimestamp},
	{collection: "memory_source_replacements", document: "*", field: "control_state/updated_at", kind: firestoreTimestamp},
	{collection: "episode_segment_receipts", document: "*", field: "updated_at", kind: firestoreTimestamp},
	{collection: "conversations", document: "*/analytics_markers/*", field: "created_at", kind: firestoreTimestamp},
	{collection: "hourly_usage", document: "*", field: "last_updated", kind: firestoreTimestamp},
}

var approvedConversationTimestampFields = map[string]bool{
	"notes_written_at":     true,
	"terminal_family_at":   true,
	"summary_completed_at": true,
}

func timestampText(value any) (string, bool) {
	wrapped, ok := value.(map[string]any)
	if !ok || len(wrapped) != 1 {
		return "", false
	}
	stamp, ok := wrapped["$timestamp"].(string)
	return stamp, ok
}

func validTimestampValue(run *observation, value any, firestore bool) bool {
	return validTimestampValueWithin(run, value, firestore, 0)
}

func validTimestampValueWithin(run *observation, value any, firestore bool, grace time.Duration) bool {
	if run == nil || run.Started.IsZero() || run.Finished.IsZero() || run.Finished.Before(run.Started) {
		return false
	}
	var stamp string
	var ok bool
	if firestore {
		stamp, ok = timestampText(value)
	} else {
		stamp, ok = value.(string)
	}
	if !ok {
		return false
	}
	parsed, err := time.Parse(time.RFC3339Nano, stamp)
	return err == nil && !parsed.Before(run.Started) && !parsed.After(run.Finished.Add(grace))
}

func timestampRuleForDocument(path, field string) (timestampRule, bool) {
	parts := strings.Split(path, "/")
	if len(parts) < 4 || parts[0] != "users" {
		return timestampRule{}, false
	}
	collection := parts[2]
	document := strings.Join(parts[3:], "/")
	for _, rule := range approvedTimestampRules {
		if collection == rule.collection && field == rule.field && pathPatternMatches(rule.document, document) {
			return rule, true
		}
	}
	return timestampRule{}, false
}

func pathPatternMatches(pattern, value string) bool {
	patternParts, valueParts := strings.Split(pattern, "/"), strings.Split(value, "/")
	if len(patternParts) != len(valueParts) {
		return false
	}
	for index, part := range patternParts {
		if part != "*" && part != valueParts[index] {
			return false
		}
	}
	return true
}

func approvedTimestampDifference(path string, python, goRun *observation) string {
	parts := pointerParts(path)
	if len(parts) >= 2 && parts[0] == "conversation" {
		field := strings.Join(parts[1:], "/")
		field = strings.TrimSuffix(field, "/$timestamp")
		if field == "updated_at" {
			if timestampInWindow(python) && timestampInWindow(goRun) {
				return "both conversation updated_at values are Firestore timestamps within their own replay windows"
			}
			return ""
		}
		if !approvedConversationTimestampFields[field] {
			return ""
		}
		pyValue, pyOK := nestedField(python.Document, field)
		goValue, goOK := nestedField(goRun.Document, field)
		if pyOK && goOK && validTimestampValue(python, pyValue, true) && validTimestampValue(goRun, goValue, true) {
			return "both conversation write clocks are Firestore timestamps within their own replay windows"
		}
		return ""
	}
	if len(parts) < 3 || parts[0] != "derived_documents" {
		return ""
	}
	docPath := parts[1]
	field := strings.Join(parts[2:], "/")
	field = strings.TrimSuffix(field, "/$timestamp")
	rule, ok := timestampRuleForDocument(docPath, field)
	if !ok {
		return ""
	}
	pyDoc, pyOK := python.Derived[docPath].(map[string]any)
	goDoc, goOK := goRun.Derived[docPath].(map[string]any)
	pyValue, pyValueOK := nestedField(pyDoc, field)
	goValue, goValueOK := nestedField(goDoc, field)
	if pyOK && goOK && pyValueOK && goValueOK &&
		validTimestampValueWithin(python, pyValue, rule.kind == firestoreTimestamp, rule.grace) &&
		validTimestampValueWithin(goRun, goValue, rule.kind == firestoreTimestamp, rule.grace) &&
		additionalTimestampRuleValid(docPath, pyDoc, field) && additionalTimestampRuleValid(docPath, goDoc, field) {
		return "both values retain the contract timestamp type and fall within their own replay windows"
	}
	return ""
}

func validateTimestampEvidence(diffs *[]difference, side string, run *observation) {
	if run == nil {
		return
	}
	conversation, _ := run.Document.(map[string]any)
	if run.UpdatedAtChanged && run.Document != nil && !timestampInWindow(run) {
		addDifference(diffs, "/"+side+"/conversation/updated_at", "invalid_clock")
	}
	for field := range approvedConversationTimestampFields {
		if value, exists := conversation[field]; exists && !validTimestampValue(run, value, true) {
			addDifference(diffs, "/"+side+"/conversation/"+field, "invalid_clock")
		}
	}
	for docPath, raw := range run.Derived {
		doc, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		validateNestedTimestampFields(diffs, side, run, docPath, doc, doc, "")
	}
}

func validateNestedTimestampFields(diffs *[]difference, side string, run *observation, docPath string, root, current map[string]any, prefix string) {
	for field, value := range current {
		fieldPath := field
		if prefix != "" {
			fieldPath = prefix + "/" + field
		}
		if rule, ok := timestampRuleForDocument(docPath, fieldPath); ok {
			if !validTimestampValueWithin(run, value, rule.kind == firestoreTimestamp, rule.grace) ||
				!additionalTimestampRuleValid(docPath, docAtPath(root, strings.Split(fieldPath, "/")), field) {
				addDifference(diffs, "/"+side+"/derived_documents/"+escapePointer(docPath)+"/"+fieldPath, "invalid_clock")
			}
			continue
		}
		if child, ok := value.(map[string]any); ok {
			validateNestedTimestampFields(diffs, side, run, docPath, root, child, fieldPath)
		}
	}
}

func docAtPath(doc map[string]any, parts []string) map[string]any {
	current := doc
	for _, part := range parts[:max(0, len(parts)-1)] {
		child, ok := current[part].(map[string]any)
		if !ok {
			return nil
		}
		current = child
	}
	return current
}

func nestedField(value any, path string) (any, bool) {
	current := value
	for _, part := range strings.Split(path, "/") {
		object, ok := current.(map[string]any)
		if !ok {
			return nil, false
		}
		current, ok = object[part]
		if !ok {
			return nil, false
		}
	}
	return current, true
}

func additionalTimestampRuleValid(path string, doc map[string]any, field string) bool {
	parts := strings.Split(path, "/")
	if field == "recorded_at" && len(parts) >= 6 && parts[4] == "goal_history" {
		stamp, ok := timestampText(doc[field])
		if !ok {
			return false
		}
		parsed, err := time.Parse(time.RFC3339Nano, stamp)
		date, dateOK := doc["date"].(string)
		return err == nil && dateOK && date == parts[len(parts)-1] && parsed.UTC().Format("2006-01-02") == date
	}
	if field == "last_updated" && len(parts) == 4 && (parts[2] == "llm_usage" || parts[2] == "hourly_usage") {
		stamp, ok := timestampText(doc[field])
		if !ok {
			return false
		}
		parsed, err := time.Parse(time.RFC3339Nano, stamp)
		return err == nil && parsed.UTC().Format("2006-01-02") == parts[3]
	}
	return true
}
