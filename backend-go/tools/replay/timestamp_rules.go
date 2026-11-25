package main

import (
	"encoding/json"
	"math"
	"strconv"
	"strings"
	"time"
)

const postFinishWriteGrace = 5 * time.Second
const memoryItemTTL = 48 * time.Hour

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
	{collection: "memory_items", document: "*", field: "updated_at", kind: firestoreTimestamp},
	{collection: "memory_items", document: "*", field: "valid_from", kind: firestoreTimestamp},
	{collection: "memory_source_replacements", document: "*", field: "committed_at", kind: firestoreTimestamp},
	{collection: "memory_source_replacements", document: "*", field: "control_state/updated_at", kind: firestoreTimestamp},
	{collection: "episode_segment_receipts", document: "*", field: "updated_at", kind: firestoreTimestamp},
	{collection: "conversations", document: "*/analytics_markers/*", field: "created_at", kind: firestoreTimestamp},
	{collection: "hourly_usage", document: "*", field: "last_updated", kind: firestoreTimestamp, grace: postFinishWriteGrace},
}

var approvedConversationTimestampFields = map[string]bool{
	"notes_written_at":   true,
	"terminal_family_at": true,
	"title_changed_at":   true,
}

var approvedConversationUnixSecondFields = map[string]bool{
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

func validTimestampValue(run *observation, value any) bool {
	return validTimestampValueWithin(run, value, true, 0)
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

func validUnixSecondValue(run *observation, value any) bool {
	if run == nil || run.Started.IsZero() || run.Finished.IsZero() || run.Finished.Before(run.Started) {
		return false
	}
	var seconds float64
	switch number := value.(type) {
	case json.Number:
		parsed, err := number.Float64()
		if err != nil {
			return false
		}
		seconds = parsed
	case float64:
		seconds = number
	case float32:
		seconds = float64(number)
	case int:
		seconds = float64(number)
	case int64:
		seconds = float64(number)
	case int32:
		seconds = float64(number)
	case uint64:
		seconds = float64(number)
	case uint32:
		seconds = float64(number)
	case uint:
		seconds = float64(number)
	default:
		return false
	}
	if math.IsNaN(seconds) || math.IsInf(seconds, 0) {
		return false
	}
	start := float64(run.Started.UnixNano()) / float64(time.Second)
	finish := float64(run.Finished.UnixNano()) / float64(time.Second)
	return seconds >= start && seconds <= finish
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
		if approvedConversationUnixSecondFields[field] {
			pyValue, pyOK := nestedField(python.Document, field)
			goValue, goOK := nestedField(goRun.Document, field)
			if pyOK && goOK && validUnixSecondValue(python, pyValue) && validUnixSecondValue(goRun, goValue) {
				return "both conversation Unix-second clocks are numeric and within their own replay windows"
			}
			return ""
		}
		if !approvedConversationTimestampFields[field] {
			return ""
		}
		pyValue, pyOK := nestedField(python.Document, field)
		goValue, goOK := nestedField(goRun.Document, field)
		if pyOK && goOK && validTimestampValue(python, pyValue) && validTimestampValue(goRun, goValue) {
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
	if memoryItemDocumentPath(docPath) && field == "expires_at" {
		pyDoc, pyOK := python.Derived[docPath].(map[string]any)
		goDoc, goOK := goRun.Derived[docPath].(map[string]any)
		if pyOK && goOK && validMemoryItemExpiry(pyDoc) && validMemoryItemExpiry(goDoc) {
			return "replay_clock"
		}
		return ""
	}
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
		additionalTimestampRuleValid(python, docPath, pyDoc, field) &&
		additionalTimestampRuleValid(goRun, docPath, goDoc, field) {
		return "both values retain the contract timestamp type and fall within their own replay windows"
	}
	return ""
}

func validateTimestampEvidence(diffs *[]difference, side string, run *observation) {
	if run == nil {
		return
	}
	conversation, ok := run.Document.(map[string]any)
	if !ok {
		if run.UpdatedAtChanged && run.Document != nil {
			addDifference(diffs, "/"+side+"/conversation/updated_at", "invalid_clock")
		}
		return
	}
	if run.UpdatedAtChanged && run.Document != nil && !timestampInWindow(run) {
		addDifference(diffs, "/"+side+"/conversation/updated_at", "invalid_clock")
	}
	for field := range approvedConversationTimestampFields {
		if value, exists := conversation[field]; exists && !validTimestampValue(run, value) {
			addDifference(diffs, "/"+side+"/conversation/"+field, "invalid_clock")
		}
	}
	for field := range approvedConversationUnixSecondFields {
		if value, exists := conversation[field]; exists && !validUnixSecondValue(run, value) {
			addDifference(diffs, "/"+side+"/conversation/"+field, "invalid_clock")
		}
	}
	for docPath, raw := range run.Derived {
		doc, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if memoryItemDocumentPath(docPath) {
			if _, exists := doc["expires_at"]; exists && !validMemoryItemExpiry(doc) {
				*diffs = append(*diffs, difference{
					Path: "/" + side + "/derived_documents/" + escapePointer(docPath) + "/expires_at",
					Kind: "invalid_ttl", FailureReason: memoryItemExpiryFailureReason(doc),
				})
			}
		}
		validateNestedTimestampFields(diffs, side, run, docPath, doc, doc, "")
	}
}

func memoryItemDocumentPath(path string) bool {
	parts := strings.Split(path, "/")
	return len(parts) == 4 && parts[0] == "users" && parts[2] == "memory_items"
}

func validMemoryItemExpiry(doc map[string]any) bool {
	expires, ok := timestampText(doc["expires_at"])
	if !ok {
		return false
	}
	created, ok := timestampText(doc["captured_at"])
	if !ok {
		return false
	}
	updated := created
	if value, exists := doc["updated_at"]; exists {
		updated, ok = timestampText(value)
		if !ok {
			return false
		}
	}
	expiresAt, err := time.Parse(time.RFC3339Nano, expires)
	if err != nil {
		return false
	}
	createdAt, err := time.Parse(time.RFC3339Nano, created)
	if err != nil {
		return false
	}
	updatedAt, err := time.Parse(time.RFC3339Nano, updated)
	if err != nil || !expiresAt.After(updatedAt) {
		return false
	}
	return expiresAt.Equal(createdAt.Add(memoryItemTTL))
}

func memoryItemExpiryFailureReason(doc map[string]any) string {
	expires, expiresOK := timestampText(doc["expires_at"])
	created, createdOK := timestampText(doc["captured_at"])
	if !expiresOK || !createdOK {
		return "missing_or_malformed_ttl_timestamp"
	}
	updated := created
	if value, exists := doc["updated_at"]; exists {
		var ok bool
		updated, ok = timestampText(value)
		if !ok {
			return "malformed_write_timestamp"
		}
	}
	expiresAt, expiresErr := time.Parse(time.RFC3339Nano, expires)
	updatedAt, updatedErr := time.Parse(time.RFC3339Nano, updated)
	if expiresErr != nil || updatedErr != nil || !expiresAt.After(updatedAt) {
		return "expiry_not_after_write"
	}
	return "outside_48_hour_ttl"
}

func validateNestedTimestampFields(diffs *[]difference, side string, run *observation, docPath string, root, current map[string]any, prefix string) {
	for field, value := range current {
		fieldPath := field
		if prefix != "" {
			fieldPath = prefix + "/" + field
		}
		if rule, ok := timestampRuleForDocument(docPath, fieldPath); ok {
			if !validTimestampValueWithin(run, value, rule.kind == firestoreTimestamp, rule.grace) ||
				!additionalTimestampRuleValid(run, docPath, docAtPath(root, strings.Split(fieldPath, "/")), field) {
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
	for part := range strings.SplitSeq(path, "/") {
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

func additionalTimestampRuleValid(run *observation, path string, doc map[string]any, field string) bool {
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
		if err != nil {
			return false
		}
		day := parsed.UTC().Format("2006-01-02")
		if parts[2] == "hourly_usage" {
			if run.HourlyUsageReplayBucket != "" {
				bucket, err := time.Parse("2006-01-02-15", run.HourlyUsageReplayBucket)
				return err == nil && parts[3] == bucket.Format("2006-01-02-15")
			}
			if parts[3] == day {
				return true
			}
			if len(parts[3]) != 13 || parts[3][:10] != day || parts[3][10] != '-' {
				return false
			}
			hour, hourErr := strconv.Atoi(parts[3][11:])
			return hourErr == nil && hour >= 0 && hour <= 23
		}
		return parts[3] == day
	}
	return true
}
