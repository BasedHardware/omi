package main

import (
	"bytes"
	"compress/zlib"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"io"
	"maps"
	"math"
	"reflect"
	"strings"
)

func measuredResolver(run *observation) map[string]any {
	trace := run.SpeakerTrace
	if trace == nil || len(trace.Exits) != 1 || run.Started.IsZero() || !run.Finished.After(run.Started) {
		return nil
	}
	diag, _ := documentField(run, "owner_recognition_diagnostics").(map[string]any)
	current, _ := diag["current_resolver"].(map[string]any)
	if current == nil || !reflect.DeepEqual(current, diag["first_resolver"]) || !reflect.DeepEqual(trace.Exits[0], current) ||
		current["uid"] != run.OwnerID || current["conversation"] != run.ConversationID || current["pass"] != "first" ||
		documentField(run, "private_cloud_sync_enabled") != false {
		return nil
	}
	if current["reason"] != "private_cloud_disabled" && current["reason"] != "empty_transcript" {
		return nil
	}
	resolution := documentField(run, "speaker_resolution")
	if (current["reason"] == "empty_transcript" && (current["status"] != "absent" || resolution != nil)) ||
		(current["reason"] == "private_cloud_disabled" && (current["status"] != "capture" || objectField(resolution, "status") != "capture")) {
		return nil
	}
	seconds, ok := current["elapsed_seconds"].(json.Number)
	n, err := seconds.Float64()
	if !ok || err != nil || math.IsNaN(n) || math.IsInf(n, 0) || n < 0 || n > run.Finished.Sub(run.Started).Seconds()+0.0005 {
		return nil
	}
	stable := maps.Clone(current)
	delete(stable, "elapsed_seconds")
	normalized := maps.Clone(diag)
	normalized["first_resolver"] = stable
	normalized["current_resolver"] = stable
	return normalized
}

func observedSpeakerPayload(run *observation, path string) []byte {
	if run.SpeakerTrace == nil || len(run.SpeakerTrace.Evidence) != 1 {
		return nil
	}
	doc, _ := run.Derived[path].(map[string]any)
	envelope, ok := doc["payload"].(string)
	if len(doc) != 2 || doc["version"] != json.Number("1") || !ok || len(envelope) > 750000 {
		return nil
	}
	encoded, err := decryptReplayEnvelope(run.OwnerID, envelope, defaultReplayTestKey)
	if err != nil {
		return nil
	}
	compressed, err := base64.StdEncoding.Strict().DecodeString(string(encoded))
	if err != nil {
		return nil
	}
	source := bytes.NewReader(compressed)
	reader, err := zlib.NewReader(source)
	if err != nil {
		return nil
	}
	payload, readErr := io.ReadAll(io.LimitReader(reader, 16000001))
	closeErr := reader.Close()
	if readErr != nil || closeErr != nil || source.Len() != 0 || len(payload) > 16000000 || !json.Valid(payload) {
		return nil
	}
	hash := sha256.Sum256(payload)
	if hex.EncodeToString(hash[:]) != run.SpeakerTrace.Evidence[0] {
		return nil
	}
	return payload
}

// Proposed for the synthetic capture-only corpus. A trace is emitted by the
// actual resolver and evidence builder independently of the stored result.
func reviewSpeakerDifferences(diffs []difference, py, goRun *observation) {
	if py.ConversationID == "" || strings.ContainsAny(py.ConversationID, "/~") || py.OwnerID != "replay-"+py.ConversationID || goRun.OwnerID != py.OwnerID || goRun.ConversationID != py.ConversationID {
		return
	}
	diag := measuredResolver(py)
	equalTime := diag != nil && reflect.DeepEqual(diag, measuredResolver(goRun))
	doc := "users/" + py.OwnerID + "/conversations/" + py.ConversationID + "/speaker_evidence/current"
	evidencePath := "/derived_documents/" + strings.ReplaceAll(doc, "/", "~1") + "/payload"
	for i, d := range diffs {
		if d.Kind != "different_value" || d.Reason != "" {
			continue
		}
		switch d.Path {
		case "/conversation/owner_recognition_diagnostics/first_resolver/elapsed_seconds", "/conversation/owner_recognition_diagnostics/current_resolver/elapsed_seconds":
			if equalTime {
				diffs[i].Reason = "replay_clock"
			}
		case evidencePath:
			p := observedSpeakerPayload(py, doc)
			if p != nil && bytes.Equal(p, observedSpeakerPayload(goRun, doc)) {
				diffs[i].Reason = "speaker_evidence_ciphertext"
			}
		}
	}
}
