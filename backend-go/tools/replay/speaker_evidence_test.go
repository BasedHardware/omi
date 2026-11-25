package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"maps"
	"strconv"
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
	duration, err := strconv.ParseFloat(elapsed, 64)
	if err != nil {
		t.Fatal(err)
	}
	run.SpeakerTrace = &speakerTrace{Exits: []map[string]any{exit}, ClockSeconds: []json.Number{"10", json.Number(strconv.FormatFloat(10+duration, 'f', -1, 64))}}
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
		"valid":             nil,
		"missing entry":     func(r *observation) { r.SpeakerTrace.ClockSeconds = r.SpeakerTrace.ClockSeconds[1:] },
		"extra reading":     func(r *observation) { r.SpeakerTrace.ClockSeconds = append(r.SpeakerTrace.ClockSeconds, "10.3") },
		"reversed interval": func(r *observation) { r.SpeakerTrace.ClockSeconds = []json.Number{"11", "10"} },
		"rounded exit and stored duration agree but interval differs": func(r *observation) { r.SpeakerTrace.ClockSeconds[1] = "10.200501" },
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
			reviewSpeakerDifferences(&diffs, py, g)
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
		"different builder bytes": func(r *observation) { setEvidence(t, r, r.OwnerID, "capturE", 4) },
		"builder mismatch":        func(r *observation) { r.SpeakerTrace.Evidence[0] = "incorrect" },
		"missing builder":         func(r *observation) { r.SpeakerTrace = nil },
		"second builder": func(r *observation) {
			r.SpeakerTrace.Evidence = append(r.SpeakerTrace.Evidence, r.SpeakerTrace.Evidence[0])
		},
		"version":          func(r *observation) { mustMap(r.Derived[speakerDoc])["version"] = json.Number("2") },
		"extra field":      func(r *observation) { mustMap(r.Derived[speakerDoc])["raw"] = "extra" },
		"wrong document":   func(r *observation) { r.Derived["other"] = r.Derived[speakerDoc]; delete(r.Derived, speakerDoc) },
		"invalid encoding": func(r *observation) { mustMap(r.Derived[speakerDoc])["payload"] = "invalid" },
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
			reviewSpeakerDifferences(&diffs, py, g)
			for i, d := range diffs {
				want := mutate == nil && i == 0
				if i == 0 && mutate != nil && d.FailureReason != "speaker_envelope_unverified" {
					t.Fatalf("missing gap for %s", d.Path)
				}
				if (d.Reason == "encrypted_envelope") != want {
					t.Fatalf("unexpected reason %q at %s", d.Reason, d.Path)
				}
			}
		})
	}
}

func TestSpeakerClockAcceptsOnlyStoredRounding(t *testing.T) {
	py, g := captureRun(t, "0.4", 1), captureRun(t, "0.2", 2)
	g.SpeakerTrace.ClockSeconds = []json.Number{"10", "10.200499"}
	diff := []difference{{Kind: "different_value", Path: clockPath}}
	reviewSpeakerDifferences(&diff, py, g)
	if diff[0].Reason != "replay_clock" {
		t.Fatalf("valid rounded duration refused: %+v", diff[0])
	}
}

func TestEqualSpeakerValuesStillRequireBothWitnesses(t *testing.T) {
	py, g := captureRun(t, "0.2", 1), captureRun(t, "0.2", 1)
	if diffs, _ := compareObservationsForRun(py, g, nil, nil); len(diffs) != 0 {
		t.Fatalf("equal, witnessed capture yielded findings: %+v", diffs)
	}
	g.SpeakerTrace = nil
	diffs, _ := compareObservationsForRun(py, g, nil, nil)
	var resolverReported, envelopeReported bool
	for _, d := range diffs {
		if d.Kind != "invalid_binding" || d.Reason != "" {
			continue
		}
		switch d.Path {
		case "/go" + clockPath:
			resolverReported = true
		case "/go/derived_documents/" + escapePointer(speakerDoc) + "/payload":
			envelopeReported = true
		}
	}
	if !resolverReported || !envelopeReported {
		t.Fatalf("expected findings for both missing Go witnesses, got %+v", diffs)
	}
}

func TestUnsampledSpeakerBuilderNeedsResolverWitnessWithoutAnEnvelope(t *testing.T) {
	py, g := captureRun(t, "0.2", 1), captureRun(t, "0.2", 1)
	delete(py.Derived, speakerDoc)
	delete(g.Derived, speakerDoc)
	g.SpeakerTrace.Evidence = nil
	if diffs, _ := compareObservationsForRun(py, g, nil, nil); len(diffs) != 0 {
		t.Fatalf("unsampled builder yielded findings: %+v", diffs)
	}
	g.SpeakerTrace = nil
	diffs, _ := compareObservationsForRun(py, g, nil, nil)
	if len(diffs) != 1 || diffs[0].Path != "/go"+clockPath || diffs[0].FailureReason != "speaker_resolver_unverified" {
		t.Fatalf("expected only the missing Go resolver witness, got %+v", diffs)
	}
}

func TestFlippedSpeakerAuthenticationTagProducesValueFreeGap(t *testing.T) {
	py, g := captureRun(t, "0.4", 1), captureRun(t, "0.2", 2)
	const marker = "synthetic-private-payload-marker"
	setEvidence(t, py, py.OwnerID, marker, 1)
	setEvidence(t, g, g.OwnerID, marker, 2)
	doc := mustMap(g.Derived[speakerDoc])
	goPayload, ok := doc["payload"].(string)
	if !ok {
		t.Fatal("speaker payload is not a string")
	}
	raw, err := base64.StdEncoding.Strict().DecodeString(goPayload)
	if err != nil {
		t.Fatal(err)
	}
	raw[len(raw)-1] ^= 1
	doc["payload"] = base64.StdEncoding.EncodeToString(raw)
	result, err := compare([]replayCase{{Name: "c", Python: py, Go: g}})
	if err != nil {
		t.Fatal(err)
	}
	path := "/derived_documents/" + strings.ReplaceAll(speakerDoc, "/", "~1") + "/payload"
	found := false
	for _, d := range result.Cases[0].Differences {
		if d.Path == path {
			found = true
			if d.Reason != "" || d.FailureReason != "speaker_envelope_unverified" {
				t.Fatalf("unexpected classification: %+v", d)
			}
		}
	}
	if !found {
		t.Fatal("missing tampered-envelope difference")
	}
	stripReportValues(&result)
	reportJSON, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	goPayload, ok = doc["payload"].(string)
	if !ok {
		t.Fatal("tampered speaker payload is not a string")
	}
	pythonPayload, ok := mustMap(py.Derived[speakerDoc])["payload"].(string)
	if !ok {
		t.Fatal("Python speaker payload is not a string")
	}
	for _, value := range []string{marker, goPayload, pythonPayload} {
		if bytes.Contains(reportJSON, []byte(value)) {
			t.Fatal("speaker payload exposed in report")
		}
	}
}
