package rules

import (
	"encoding/json"
	"strings"
	"unicode/utf8"
)

// TaskKind selects the protocol only after the entry point authenticates the request.
type TaskKind uint8

// Task protocols share the Python task endpoint.
const (
	TaskInvalid TaskKind = iota
	TaskInvalidEnrichment
	TaskOrdinary
	TaskQuiet
	TaskMerge
	TaskEnrichment
)

// Task is an envelope with either a job generation or an enrichment binding.
type Task struct {
	Kind       TaskKind
	JobID      string
	Generation int64
	Key, Token string
}

// DecodeTask parses the two disjoint protocols and routes the reserved prefixes.
// HTTP acknowledgement and work ownership belong to the consuming endpoint.
func DecodeTask(body []byte) Task {
	var fields map[string]json.RawMessage
	if json.Unmarshal(body, &fields) != nil {
		return Task{}
	}
	if text(fields["kind"]) == "sync_reprocess" {
		key, token := text(fields["key"]), text(fields["task_token"])
		if len(fields) != 3 || !lowerHex(key, 64) || !lowerHex(token, 32) {
			return Task{Kind: TaskInvalidEnrichment}
		}
		return Task{Kind: TaskEnrichment, Key: key, Token: token}
	}
	id := text(fields["job_id"])
	var generation int64
	if len(fields) != 2 || id == "" || utf8.RuneCountInString(id) > 128 ||
		json.Unmarshal(fields["dispatch_generation"], &generation) != nil || generation <= 0 {
		return Task{}
	}
	kind := TaskOrdinary
	switch {
	case strings.HasPrefix(id, "quiet-"):
		kind = TaskQuiet
	case strings.HasPrefix(id, "merge-"):
		kind = TaskMerge
	}
	return Task{Kind: kind, JobID: id, Generation: generation}
}

func text(value json.RawMessage) string {
	var result string
	if json.Unmarshal(value, &result) != nil {
		return ""
	}
	return result
}

func lowerHex(value string, length int) bool {
	if len(value) != length {
		return false
	}
	for _, digit := range value {
		if (digit < '0' || digit > '9') && (digit < 'a' || digit > 'f') {
			return false
		}
	}
	return true
}
