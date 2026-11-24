package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"maps"
	"strings"
	"testing"
	"time"
)

const speakerDoc = "users/replay-c/conversations/c/speaker_evidence/current"
const clockPath = "/conversation/owner_recognition_diagnostics/current_resolver/elapsed_seconds"

func captureRun(t *testing.T, elapsed string, nonce byte) *observation {
	t.Helper()
	run := ruleRun()
	run.OwnerID = "replay-c"
	exit := map[string]any{"uid": run.OwnerID, "conversation": "c", "pass": "first", "reason": "private_cloud_disabled", "status": "capture", "elapsed_seconds": json.Number(elapsed)}
	run.Document = map[string]any{"private_cloud_sync_enabled": false, "speaker_resolution": map[string]any{"status": "capture"}, "owner_recognition_diagnostics": map[string]any{"current_resolver": maps.Clone(exit), "first_resolver": maps.Clone(exit)}}
	run.SpeakerTrace = &speakerTrace{Exits: []map[string]any{exit}}
	setEvidence(t, run, run.OwnerID, "capture", nonce)
	return run
}

func setEvidence(t *testing.T, run *observation, uid, label string, nonce byte) {
	t.Helper()
	data := map[string]any{"status": label, "version": 1}
	raw, err := json.Marshal(data)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(raw)
	run.SpeakerTrace.Evidence = []string{hex.EncodeToString(sum[:])}
	run.Derived[speakerDoc] = map[string]any{"version": json.Number("1"), "payload": sealReplayValue(t, uid, base64.StdEncoding.EncodeToString(compressedJSON(t, data)), nonce)}
}

func TestSpeakerClockRequiresRunAndWriteWitness(t *testing.T) {
	tests := map[string]func(*observation){
		"valid":                   nil,
		"no measurement":          func(r *observation) { r.SpeakerTrace = nil },
		"multiple measurements":   func(r *observation) { r.SpeakerTrace.Exits = append(r.SpeakerTrace.Exits, r.SpeakerTrace.Exits[0]) },
		"wrong account":           func(r *observation) { r.OwnerID = "different" },
		"wrong conversation":      func(r *observation) { r.ConversationID = "different" },
		"cloud consent changed":   func(r *observation) { mustMap(r.Document)["private_cloud_sync_enabled"] = true },
		"resolution status drift": func(r *observation) { mustMap(documentField(r, "speaker_resolution"))["status"] = "resolved" },
		"first differs from current": func(r *observation) {
			mustMap(mustMap(documentField(r, "owner_recognition_diagnostics"))["first_resolver"])["elapsed_seconds"] = json.Number("2")
		},
		"receipt differs from measurement": func(r *observation) { r.SpeakerTrace.Exits[0]["elapsed_seconds"] = json.Number("2") },
		"outside execution window":         func(r *observation) { r.Finished = r.Started.Add(time.Millisecond) },
		"live metadata differs": func(r *observation) {
			mustMap(documentField(r, "owner_recognition_diagnostics"))["live"] = []any{"different"}
		},
		"different reason or scope": func(r *observation) {
			row := r.SpeakerTrace.Exits[0]
			row["scope"] = "other"
			diag := mustMap(documentField(r, "owner_recognition_diagnostics"))
			diag["first_resolver"] = maps.Clone(row)
			diag["current_resolver"] = maps.Clone(row)
		},
	}
	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			py, g := captureRun(t, "0.4", 1), captureRun(t, "0.2", 2)
			if mutate != nil {
				mutate(g)
			}
			diffs := []difference{{Kind: "different_value", Path: clockPath}, {Kind: "different_value", Path: strings.Replace(clockPath, "current", "first", 1)}, {Kind: "different_value", Path: "/other/elapsed_seconds"}, {Kind: "missing_in_go", Path: clockPath}}
			reviewSpeakerDifferences(diffs, py, g)
			for i, d := range diffs {
				want := mutate == nil && i < 2
				if (d.Reason == "replay_clock") != want {
					t.Fatalf("unexpected reason %q at %s", d.Reason, d.Path)
				}
			}
		})
	}
}

func TestSpeakerCiphertextRequiresEqualAuthenticatedBuilderBytes(t *testing.T) {
	tests := map[string]func(*observation){
		"valid":                   nil,
		"wrong key":               func(r *observation) { setEvidence(t, r, "foreign", "capture", 4) },
		"different builder bytes": func(r *observation) { setEvidence(t, r, r.OwnerID, "different", 4) },
		"builder mismatch":        func(r *observation) { r.SpeakerTrace.Evidence[0] = "incorrect" },
		"missing builder":         func(r *observation) { r.SpeakerTrace = nil },
		"second builder": func(r *observation) {
			r.SpeakerTrace.Evidence = append(r.SpeakerTrace.Evidence, r.SpeakerTrace.Evidence[0])
		},
		"version":        func(r *observation) { mustMap(r.Derived[speakerDoc])["version"] = json.Number("2") },
		"extra field":    func(r *observation) { mustMap(r.Derived[speakerDoc])["raw"] = "extra" },
		"wrong document": func(r *observation) { r.Derived["other"] = r.Derived[speakerDoc]; delete(r.Derived, speakerDoc) },
		"tampered":       func(r *observation) { mustMap(r.Derived[speakerDoc])["payload"] = "invalid" },
		"invalid compression": func(r *observation) {
			mustMap(r.Derived[speakerDoc])["payload"] = sealReplayValue(t, r.OwnerID, "Zg==", 1)
		},
		"oversize envelope": func(r *observation) { mustMap(r.Derived[speakerDoc])["payload"] = strings.Repeat("a", 750001) },
		"trailing compressed bytes": func(r *observation) {
			data := append(compressedJSON(t, map[string]any{"status": "capture", "version": 1}), 0)
			mustMap(r.Derived[speakerDoc])["payload"] = sealReplayValue(t, r.OwnerID, base64.StdEncoding.EncodeToString(data), 1)
		},
	}
	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			py, g := captureRun(t, "0.4", 1), captureRun(t, "0.2", 2)
			if mutate != nil {
				mutate(g)
			}
			path := "/derived_documents/" + strings.ReplaceAll(speakerDoc, "/", "~1") + "/payload"
			diffs := []difference{{Kind: "different_value", Path: path}, {Kind: "different_value", Path: path + "2"}, {Kind: "missing_in_go", Path: path}}
			reviewSpeakerDifferences(diffs, py, g)
			for i, d := range diffs {
				want := mutate == nil && i == 0
				if (d.Reason == "speaker_evidence_ciphertext") != want {
					t.Fatalf("unexpected reason %q at %s", d.Reason, d.Path)
				}
			}
		})
	}
}
