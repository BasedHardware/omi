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
	"strings"
)

func measuredResolver(run *observation) map[string]any {
	trace := run.SpeakerTrace
	if trace == nil || len(trace.Exits) != 1 || len(trace.ClockSeconds) != 2 || run.Started.IsZero() || !run.Finished.After(run.Started) {
		return nil
	}
	diag, ok := documentField(run, "owner_recognition_diagnostics").(map[string]any)
	if !ok {
		return nil
	}
	current, ok := diag["current_resolver"].(map[string]any)
	if !ok || !equalReplayValue(current, diag["first_resolver"]) || !equalReplayValue(trace.Exits[0], current) ||
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
	// Stored durations are rounded to the nearest millisecond. Each side
	// must agree with its own unrounded monotonic entry and exit readings.
	entry, entryErr := trace.ClockSeconds[0].Float64()
	exit, exitErr := trace.ClockSeconds[1].Float64()
	interval := exit - entry
	if entryErr != nil || exitErr != nil || !(entry >= 0 && exit >= entry) ||
		!(math.Abs(n-interval) <= 0.0005) || math.Round(n*1000)/1000 != n {
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
	doc, ok := run.Derived[path].(map[string]any)
	if !ok {
		return nil
	}
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

// Approved for the synthetic capture-only corpus. A trace is emitted by the
// actual resolver and evidence builder independently of the stored result.
func reviewSpeakerDifferences(diffs *[]difference, py, goRun *observation) {
	if py.ConversationID == "" || strings.ContainsAny(py.ConversationID, "/~") || py.OwnerID != "replay-"+py.ConversationID || goRun.OwnerID != py.OwnerID || goRun.ConversationID != py.ConversationID {
		return
	}
	pyDiag, goDiag := measuredResolver(py), measuredResolver(goRun)
	doc := "users/" + py.OwnerID + "/conversations/" + py.ConversationID + "/speaker_evidence/current"
	docPath := "/derived_documents/" + escapePointer(doc)
	_, pyStored := py.Derived[doc]
	_, goStored := goRun.Derived[doc]
	resolverExpected := expectsResolverWitness(py) || expectsResolverWitness(goRun)
	if resolverExpected {
		validateResolverWitness(diffs, "/python", pyDiag)
	}
	goDeparted := provedJobdDeparture(goRun)
	goHasResolver := documentField(goRun, "owner_recognition_diagnostics") != nil ||
		documentField(goRun, "speaker_resolution") != nil ||
		(goRun.SpeakerTrace != nil && (len(goRun.SpeakerTrace.Exits) != 0 || len(goRun.SpeakerTrace.ClockSeconds) != 0))
	if (resolverExpected && !goDeparted) || (goDeparted && goHasResolver) {
		validateResolverWitness(diffs, "/go", goDiag)
	}
	var pyPayload, goPayload []byte
	// Unsampled shadow processing can build evidence without persisting it.
	if pyStored || goStored {
		pyPayload, goPayload = observedSpeakerPayload(py, doc), observedSpeakerPayload(goRun, doc)
		validateSpeakerEnvelope(diffs, "/python", docPath, pyPayload)
		validateSpeakerEnvelope(diffs, "/go", docPath, goPayload)
	}
	for i, d := range *diffs {
		if d.Kind != "different_value" || d.Reason != "" {
			continue
		}
		switch d.Path {
		case resolverPath + "/first_resolver/elapsed_seconds", resolverPath + "/current_resolver/elapsed_seconds":
			if pyDiag != nil && equalReplayValue(pyDiag, goDiag) {
				(*diffs)[i].Reason = "replay_clock"
			}
		case docPath + "/payload":
			if pyPayload != nil && bytes.Equal(pyPayload, goPayload) {
				(*diffs)[i].Reason = "encrypted_envelope"
			} else {
				(*diffs)[i].FailureReason = "speaker_envelope_unverified"
			}
		}
	}
}

const resolverPath = "/conversation/owner_recognition_diagnostics"

// Use the post-event observation to prove an absent conversation.
func provedJobdDeparture(run *observation) bool {
	if run.Document != nil || run.OwnerID != "replay-"+run.ConversationID {
		return false
	}
	job := run.GoEvidence["job"]
	switch run.ConversationID {
	case "worker-missing-row-fence":
		return run.Status == "fenced" && objectField(job, "outcome") == "fenced" &&
			len(run.ProviderCalls) == 0
	case "erase-removes-owner-and-jobs":
		erasure := run.GoEvidence["erasure"]
		jobs, jobsOK := integerValue(objectField(erasure, "jobs_for_uid"))
		tenants, tenantsOK := integerValue(objectField(erasure, "tenants_for_uid"))
		return completedErasure(run) && equalReplayValue(erasure, run.Effects["erasure"]) &&
			objectField(job, "state") == "completed" && jobsOK && tenantsOK && jobs == 0 && tenants == 0
	default:
		return false
	}
}

func expectsResolverWitness(run *observation) bool {
	if documentField(run, "private_cloud_sync_enabled") == false &&
		objectField(documentField(run, "speaker_resolution"), "status") == "capture" {
		return true
	}
	diag := documentField(run, "owner_recognition_diagnostics")
	for _, field := range []string{"first_resolver", "current_resolver"} {
		if isCaptureResolver(objectField(diag, field)) {
			return true
		}
	}
	if run.SpeakerTrace != nil {
		for _, exit := range run.SpeakerTrace.Exits {
			if isCaptureResolver(exit) {
				return true
			}
		}
	}
	return false
}

func isCaptureResolver(row any) bool {
	reason := objectField(row, "reason")
	return reason == "private_cloud_disabled" || reason == "empty_transcript"
}

func validateResolverWitness(diffs *[]difference, side string, diag map[string]any) {
	if diag == nil {
		markSyncWriteFailure(diffs, "speaker_resolver_unverified", side+resolverPath+"/current_resolver/elapsed_seconds", func(path string) bool {
			return path == resolverPath || strings.HasPrefix(path, resolverPath+"/first_resolver/") ||
				strings.HasPrefix(path, resolverPath+"/current_resolver/") ||
				path == resolverPath+"/first_resolver" || path == resolverPath+"/current_resolver"
		})
	}
}

func validateSpeakerEnvelope(diffs *[]difference, side, docPath string, payload []byte) {
	if payload == nil {
		markSyncWriteFailure(diffs, "speaker_envelope_unverified", side+docPath+"/payload", func(path string) bool {
			return path == docPath || strings.HasPrefix(path, docPath+"/")
		})
	}
}
