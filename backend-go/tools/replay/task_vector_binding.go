package main

import (
	"encoding/json"
	"maps"
	"reflect"
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
	row, _ := rows[0].(map[string]any)
	return row
}

func taskClock(run *observation, value any) (time.Time, bool) {
	fields, ok := value.(map[string]any)
	text, _ := fields["$timestamp"].(string)
	t, err := time.Parse(time.RFC3339Nano, text)
	return t, ok && len(fields) == 1 && err == nil && !run.Started.IsZero() && !t.Before(run.Started) && !t.After(run.Finished)
}

func singleTaskBinding(run *observation) (taskBinding, bool) {
	var b taskBinding
	if run.OwnerID == "" || run.ConversationID == "" || strings.Contains(run.OwnerID, "/") || documentField(run, "id") != run.ConversationID {
		return b, false
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
		b.task, _ = raw.(map[string]any)
	}
	id := strings.TrimPrefix(b.path, prefix)
	b.item = singleObject(objectField(documentField(run, "structured"), "action_items"))
	provenance := singleObject(b.task["provenance"])
	segments, _ := b.item["source_segment_ids"].([]any)
	description, _ := b.item["description"].(string)
	if id == "" || b.task["source"] != "conversation" || b.task["owner"] != "user" || b.task["conversation_id"] != run.ConversationID ||
		b.item["capture_owner"] != "user" || description != "Send the meeting notes" || b.task["description"] != description ||
		provenance["scope"] != "canonical" || provenance["kind"] != "conversation" || provenance["id"] != run.ConversationID ||
		len(segments) != 1 || segments[0] != "segment-1" || !reflect.DeepEqual(provenance["transcript_segment_ids"], segments) {
		return b, false
	}
	created, ok := taskClock(run, b.task["created_at"])
	updated, updatedOK := taskClock(run, b.task["updated_at"])
	if !ok || !updatedOK || updated.Before(created) || !reflect.DeepEqual(b.task["created_at"], b.item["created_at"]) {
		return b, false
	}
	entry := singleObject(run.Effects["other_vectors"])
	b.vector, _ = entry["record"].(map[string]any)
	b.metadata, _ = b.vector["metadata"].(map[string]any)
	stamp, _ := b.metadata["created_at"].(json.Number)
	seconds, err := stamp.Int64()
	embedding, _ := b.vector["values"].([]any)
	if len(embedding) == 0 || entry["namespace"] != "ns4" || b.vector["id"] != run.OwnerID+"-ai-"+id || b.metadata["uid"] != run.OwnerID ||
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

func reviewSingleTaskBinding(diffs []difference, python, goRun *observation) {
	// This first-create fixture seeds no task or vector. Multiple creations and
	// refresh/reuse require separate evidence and stay on the literal comparator.
	if python.OwnerID != "replay-kept-with-effects" || python.ConversationID != "kept-with-effects" ||
		python.OwnerID != goRun.OwnerID || python.ConversationID != goRun.ConversationID {
		return
	}
	py, ok := singleTaskBinding(python)
	if !ok {
		return
	}
	goTask, ok := singleTaskBinding(goRun)
	if !ok {
		return
	}
	pyPath, goPath := py.path, goTask.path
	py.path = ""
	goTask.path = ""
	if !reflect.DeepEqual(py, goTask) {
		return
	}
	docPath := func(path string) string { return "/derived_documents/" + strings.ReplaceAll(path, "/", "~1") }
	for i, d := range diffs {
		if d.Reason != "" {
			continue
		}
		switch {
		case d.Path == docPath(pyPath) && (d.Kind == "missing_in_go" || d.Kind == "unported"),
			d.Path == docPath(goPath) && d.Kind == "missing_in_python":
			diffs[i].Reason = "task_vector_identity"
		case d.Kind == "different_value":
			switch d.Path {
			case "/effects/other_vectors/0/record/id", "/effects/other_vectors/0/record/metadata/action_item_id":
				diffs[i].Reason = "task_vector_identity"
			case "/effects/other_vectors/0/record/metadata/created_at", "/conversation/structured/action_items/0/created_at/$timestamp":
				diffs[i].Reason = "replay_clock"
			}
		}
	}
}
