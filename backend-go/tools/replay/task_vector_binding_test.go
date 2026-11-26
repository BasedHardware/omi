package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"
)

func taskProofRun(id string) *observation {
	start := time.Date(2026, 11, 24, 13, 0, 0, 0, time.UTC)
	stamp := map[string]any{"$timestamp": start.Add(time.Second).Format(time.RFC3339Nano)}
	owner, cid := "replay-kept-with-effects", "kept-with-effects"
	segments := []any{"segment-1"}
	item := map[string]any{"created_at": stamp, "capture_owner": "user", "description": "Send the meeting notes", "source_segment_ids": segments}
	task := map[string]any{"source": "conversation", "owner": "user", "conversation_id": cid, "description": item["description"], "created_at": stamp, "updated_at": stamp,
		"provenance": []any{map[string]any{"scope": "canonical", "kind": "conversation", "id": cid, "transcript_segment_ids": segments}}}
	return &observation{OwnerID: owner, ConversationID: cid, Started: start, Finished: start.Add(time.Minute),
		TaskWrites:          []string{"users/" + owner + "/action_items/" + id},
		TaskEmbeddingInputs: map[string][]string{owner + "-ai-" + id: {fmt.Sprintf("%x", sha256.Sum256([]byte("Send the meeting notes")))}},
		Document:            map[string]any{"id": cid, "structured": map[string]any{"action_items": []any{item}}},
		Derived:             map[string]any{"users/" + owner + "/action_items/" + id: task},
		Effects: map[string]any{"other_vectors": []any{map[string]any{"namespace": "ns4", "record": map[string]any{
			"id": owner + "-ai-" + id, "values": []any{json.Number("0.5")}, "metadata": map[string]any{"uid": owner, "action_item_id": id, "created_at": json.Number("1795525202")}}}}},
	}
}

func TestOnlySameAuthorizedTaskAndVectorMayPair(t *testing.T) {
	a, b := strings.Repeat("A", 20), strings.Repeat("B", 20)
	for _, change := range []string{"", "orphan", "vector points to different task", "wrong owner", "clock", "payload", "provenance", "embedding", "embedding input", "extra task", "second task write", "extra vector", "missing vector"} {
		py, goRun := taskProofRun(a), taskProofRun(b)
		taskPath := "users/" + goRun.OwnerID + "/action_items/" + b
		task := mustMap(goRun.Derived[taskPath])
		vec := mustMap(singleObject(goRun.Effects["other_vectors"])["record"])
		meta := mustMap(vec["metadata"])
		switch change {
		case "orphan":
			meta["action_item_id"] = a
		case "vector points to different task":
			otherTask := strings.Repeat("C", 20)
			vec["id"] = goRun.OwnerID + "-ai-" + otherTask
			meta["action_item_id"] = otherTask
		case "wrong owner":
			meta["uid"] = "other"
		case "clock":
			meta["created_at"] = json.Number("0")
		case "payload":
			task["completed"] = true
		case "provenance":
			singleObject(task["provenance"])["id"] = "other"
		case "embedding":
			vec["values"] = []any{json.Number("0.25")}
		case "embedding input":
			goRun.TaskEmbeddingInputs[goRun.OwnerID+"-ai-"+b] = []string{fmt.Sprintf("%x", sha256.Sum256([]byte("Different text")))}
		case "extra task":
			goRun.Derived[taskPath+"X"] = task
		case "second task write":
			goRun.TaskWrites = append(goRun.TaskWrites, taskPath)
		case "extra vector":
			goRun.Effects["other_vectors"] = append(mustSlice(goRun.Effects["other_vectors"]), vec)
		case "missing vector":
			delete(goRun.Effects, "other_vectors")
		}
		diffs := []difference{{Path: "/effects/other_vectors/0/record/id", Kind: "different_value"}}
		reviewSingleTaskBinding(diffs, py, goRun)
		if (diffs[0].Reason != "") != (change == "") {
			t.Errorf("mutation %q produced reason %q", change, diffs[0].Reason)
		}
	}
}

func receiptTestObject(t *testing.T, value any) map[string]any {
	t.Helper()
	object, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("fixture expected an object, got %T", value)
	}
	return object
}

func TestNotesReceiptClockNeedsBothDigestsAndWholeStructuredOutput(t *testing.T) {
	for _, mutation := range []string{"", "bad witness", "missing receipt", "missing witness", "different input", "other notes field", "different action", "outside window", "second task"} {
		py, g := taskProofRun(strings.Repeat("A", 20)), taskProofRun(strings.Repeat("B", 20))
		for i, r := range []*observation{py, g} {
			row := receiptTestObject(t, r.Document)
			row["notes_llm_input_hash"] = strings.Repeat("a", 64)
			r.ObservedNotesOutput = fmt.Sprintf("%064x", i+1)
			row["notes_llm_output_hash"] = r.ObservedNotesOutput
			// Each run has its own witnessed item creation timestamp.
			stamp := receiptTestObject(t, singleObject(objectField(row["structured"], "action_items"))["created_at"])
			stamp["$timestamp"] = r.Started.Add(time.Second + time.Duration(i)).Format(time.RFC3339Nano)
		}
		row := receiptTestObject(t, g.Document)
		structured := receiptTestObject(t, row["structured"])
		switch mutation {
		case "bad witness":
			g.ObservedNotesOutput = strings.Repeat("f", 64)
		case "missing receipt":
			delete(row, "notes_llm_output_hash")
		case "missing witness":
			g.ObservedNotesOutput = ""
		case "different input":
			row["notes_llm_input_hash"] = strings.Repeat("b", 64)
		case "other notes field":
			structured["gist"] = "Changed"
		case "different action":
			singleObject(structured["action_items"])["completed"] = true
		case "outside window":
			singleObject(structured["action_items"])["created_at"] = map[string]any{"$timestamp": g.Finished.Add(time.Second).Format(time.RFC3339Nano)}
		case "second task":
			g.TaskWrites = append(g.TaskWrites, g.TaskWrites[0])
		}
		diff := []difference{{Path: "/conversation/notes_llm_output_hash", Kind: "different_value"}}
		reviewSingleTaskBinding(diff, py, g)
		if (diff[0].Reason == "replay_clock") != (mutation == "") {
			t.Fatalf("%s: %s", mutation, diff[0].Reason)
		}
	}
}

func TestCopiedNotesReceiptFailsWithValidTaskBinding(t *testing.T) {
	py, g := taskProofRun(strings.Repeat("A", 20)), taskProofRun(strings.Repeat("B", 20))
	g.Admitted = &admission{Engine: "go"}
	py.ObservedNotesOutput = strings.Repeat("a", 64)
	g.ObservedNotesOutput = strings.Repeat("b", 64)
	for _, run := range []*observation{py, g} {
		row := mustMap(run.Document)
		row["notes_llm_input_hash"] = strings.Repeat("c", 64)
		row["notes_llm_output_hash"] = py.ObservedNotesOutput
	}
	stamp := mustMap(singleObject(objectField(documentField(g, "structured"), "action_items"))["created_at"])
	stamp["$timestamp"] = g.Started.Add(time.Second + time.Nanosecond).Format(time.RFC3339Nano)

	diffs, _ := compareObservationsForRun(py, g, nil, nil)
	var clockAllowed, hashReported bool
	for _, d := range diffs {
		switch d.Path {
		case "/conversation/structured/action_items/0/created_at/$timestamp":
			clockAllowed = d.Reason == "generated_identity"
		case "/go/conversation/notes_llm_output_hash":
			hashReported = d.Kind == "invalid_binding" && d.Reason == ""
		}
	}
	if !clockAllowed || !hashReported {
		t.Fatalf("expected accepted task clock and a stale Go notes hash finding, got %+v", diffs)
	}
}
