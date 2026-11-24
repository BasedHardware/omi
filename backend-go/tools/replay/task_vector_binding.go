package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"maps"
	"regexp"
	"strings"
	"time"
)

var replayTaskID = regexp.MustCompile(`^[a-zA-Z0-9]{20}$`)

type taskBinding struct {
	path                         string
	item, task, vector, metadata map[string]any
}

func singleObject(value any) map[string]any {
	rows, ok := value.([]any)
	if !ok || len(rows) != 1 {
		return nil
	}
	row, ok := rows[0].(map[string]any)
	if !ok {
		return nil
	}
	return row
}

func taskClock(run *observation, value any) (time.Time, bool) {
	fields, ok := value.(map[string]any)
	if !ok {
		return time.Time{}, false
	}
	text, ok := fields["$timestamp"].(string)
	if !ok {
		return time.Time{}, false
	}
	t, err := time.Parse(time.RFC3339Nano, text)
	return t, len(fields) == 1 && err == nil && !run.Started.IsZero() && !t.Before(run.Started) && !t.After(run.Finished)
}

func singleTaskBinding(run *observation) (taskBinding, bool) {
	var b taskBinding
	if run.OwnerID == "" || run.ConversationID == "" || strings.Contains(run.OwnerID, "/") ||
		documentField(run, "id") != run.ConversationID || len(run.Effects) != 1 || len(run.TaskWrites) != 1 {
		return b, false
	}
	for path, source := range run.FirestoreOperationSources {
		if strings.Contains(path, "/action_items/") && (source.Writes != 0 || source.Deletes != 0) {
			return b, false
		}
	}
	prefix := "users/" + run.OwnerID + "/action_items/"
	for path, raw := range run.Derived {
		if !strings.HasPrefix(path, prefix) {
			continue
		}
		if b.path != "" || !replayTaskID.MatchString(strings.TrimPrefix(path, prefix)) {
			return b, false
		}
		b.path = path
		var ok bool
		b.task, ok = raw.(map[string]any)
		if !ok {
			return b, false
		}
	}
	id := strings.TrimPrefix(b.path, prefix)
	b.item = singleObject(objectField(documentField(run, "structured"), "action_items"))
	if b.item == nil || b.task == nil {
		return b, false
	}
	provenance := singleObject(b.task["provenance"])
	segments, segmentsOK := b.item["source_segment_ids"].([]any)
	description, descriptionOK := b.item["description"].(string)
	if id == "" || run.TaskWrites[0] != b.path || b.task["source"] != "conversation" || b.task["owner"] != "user" || b.task["conversation_id"] != run.ConversationID ||
		!segmentsOK || !descriptionOK || b.item["capture_owner"] != "user" || description != "Send the meeting notes" || b.task["description"] != description ||
		provenance["scope"] != "canonical" || provenance["kind"] != "conversation" || provenance["id"] != run.ConversationID ||
		len(segments) != 1 || segments[0] != "segment-1" || !equalReplayValue(provenance["transcript_segment_ids"], segments) {
		return b, false
	}
	created, ok := taskClock(run, b.task["created_at"])
	updated, updatedOK := taskClock(run, b.task["updated_at"])
	itemCreated, itemCreatedOK := taskClock(run, b.item["created_at"])
	if !ok || !updatedOK || !itemCreatedOK || updated.Before(created) || !itemCreated.Equal(created) {
		return b, false
	}
	entry := singleObject(run.Effects["other_vectors"])
	if entry == nil {
		return b, false
	}
	var vectorOK, metadataOK bool
	b.vector, vectorOK = entry["record"].(map[string]any)
	if !vectorOK {
		return b, false
	}
	b.metadata, metadataOK = b.vector["metadata"].(map[string]any)
	if !metadataOK {
		return b, false
	}
	stamp, stampOK := b.metadata["created_at"].(json.Number)
	if !stampOK {
		return b, false
	}
	seconds, err := stamp.Int64()
	embedding, embeddingOK := b.vector["values"].([]any)
	if !embeddingOK {
		return b, false
	}
	vectorID := run.OwnerID + "-ai-" + id
	inputs := run.TaskEmbeddingInputs[vectorID]
	if len(run.TaskEmbeddingInputs) != 1 || len(inputs) != 1 || inputs[0] != fmt.Sprintf("%x", sha256.Sum256([]byte(description))) ||
		len(embedding) == 0 || entry["namespace"] != "ns4" || b.vector["id"] != vectorID || b.metadata["uid"] != run.OwnerID ||
		b.metadata["action_item_id"] != id || err != nil || seconds < updated.Unix() || seconds > run.Finished.Unix() {
		return b, false
	}
	// Compare the entire extracted task, persisted task and vector after validating
	// the fields whose values depend on this run's clock and generated document ID.
	b.item = maps.Clone(b.item)
	delete(b.item, "created_at")
	b.task = maps.Clone(b.task)
	delete(b.task, "created_at")
	delete(b.task, "updated_at")
	b.vector = maps.Clone(b.vector)
	delete(b.vector, "metadata")
	delete(b.vector, "id")
	b.metadata = maps.Clone(b.metadata)
	delete(b.metadata, "action_item_id")
	delete(b.metadata, "created_at")
	return b, true
}

func reviewSingleTaskBinding(diffs []difference, python, goRun *observation) bool {
	// This first-create fixture seeds no task or vector. Multiple creations and
	// refresh/reuse require separate evidence and stay on the literal comparator.
	if python.OwnerID != "replay-kept-with-effects" || python.ConversationID != "kept-with-effects" ||
		python.OwnerID != goRun.OwnerID || python.ConversationID != goRun.ConversationID {
		return false
	}
	py, ok := singleTaskBinding(python)
	if !ok {
		return false
	}
	goTask, ok := singleTaskBinding(goRun)
	if !ok {
		return false
	}
	pyPath, goPath := py.path, goTask.path
	py.path = ""
	goTask.path = ""
	if !equalReplayValue(py.item, goTask.item) || !equalReplayValue(py.task, goTask.task) ||
		!equalReplayValue(py.vector, goTask.vector) || !equalReplayValue(py.metadata, goTask.metadata) {
		return false
	}
	docPath := func(path string) string { return "/derived_documents/" + strings.ReplaceAll(path, "/", "~1") }
	for i, d := range diffs {
		if d.Reason != "" {
			continue
		}
		switch {
		case d.Path == docPath(pyPath) && (d.Kind == "missing_in_go" || d.Kind == "unported"),
			d.Path == docPath(goPath) && d.Kind == "missing_in_python":
			diffs[i].Reason = "generated_identity"
		case d.Kind == "different_value":
			switch d.Path {
			case "/effects/other_vectors/0/record/id", "/effects/other_vectors/0/record/metadata/action_item_id",
				"/effects/other_vectors/0/record/metadata/created_at", "/conversation/structured/action_items/0/created_at/$timestamp":
				diffs[i].Reason = "generated_identity"
			}
		}
	}
	return true
}
