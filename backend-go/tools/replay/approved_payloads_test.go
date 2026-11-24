package main

import (
	"bytes"
	"compress/zlib"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hkdf"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"strings"
	"testing"
)

func sealReplayValue(t *testing.T, uid, plaintext string, nonceByte byte) string {
	t.Helper()
	key, err := hkdf.Key(sha256.New, []byte(defaultReplayTestKey), []byte(uid), "user-data-encryption", 32)
	if err != nil {
		t.Fatal(err)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		t.Fatal(err)
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		t.Fatal(err)
	}
	nonce := bytes.Repeat([]byte{nonceByte}, aead.NonceSize())
	sealed := append([]byte(nil), nonce...)
	sealed = aead.Seal(sealed, nonce, []byte(plaintext), nil)
	return base64.StdEncoding.EncodeToString(sealed)
}

func encryptedTranscript(t *testing.T, segments any, nonceByte byte) string {
	t.Helper()
	const uid = "synthetic-owner"
	plain, err := json.Marshal(segments)
	if err != nil {
		t.Fatal(err)
	}
	var compressed bytes.Buffer
	writer := zlib.NewWriter(&compressed)
	if _, err := writer.Write(plain); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return sealReplayValue(t, uid, hex.EncodeToString(compressed.Bytes()), nonceByte)
}

func compressedJSON(t *testing.T, value any) []byte {
	t.Helper()
	return compressedJSONLevel(t, value, zlib.DefaultCompression)
}

func compressedJSONLevel(t *testing.T, value any, level int) []byte {
	t.Helper()
	plain, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	var compressed bytes.Buffer
	writer, err := zlib.NewWriterLevel(&compressed, level)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := writer.Write(plain); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return compressed.Bytes()
}

func encryptedCorrections(t *testing.T, uid string, corrections any, nonceByte byte) string {
	t.Helper()
	return sealReplayValue(t, uid, hex.EncodeToString(compressedJSON(t, corrections)), nonceByte)
}

func TestProtectedFieldsAllowDifferentNoncesOnlyForEqualPlaintext(t *testing.T) {
	uid := "synthetic-owner"
	python, goRun := ruleRun(), ruleRun()
	python.OwnerID, goRun.OwnerID = uid, uid
	segments := []any{map[string]any{
		"text": "agenda", "start": json.Number("0"), "end": json.Number("1"),
		"speaker": "SPEAKER_00", "is_user": true,
	}}
	python.Document = map[string]any{
		"transcript_segments":            encryptedTranscript(t, segments, 1),
		"transcript_segments_compressed": true,
		"home_display":                   sealReplayValue(t, uid, `{"schema":"home-v1","title":"Agenda"}`, 2),
	}
	goRun.Document = map[string]any{
		"transcript_segments":            encryptedTranscript(t, segments, 3),
		"transcript_segments_compressed": true,
		"home_display":                   sealReplayValue(t, uid, `{"schema":"home-v1","title":"Agenda"}`, 4),
	}
	pyContent := sealReplayValue(t, uid, `{"title":"Agenda","lede":"Review"}`, 5)
	goContent := sealReplayValue(t, uid, `{"title":"Agenda","lede":"Review"}`, 6)
	pyDisplay := sealReplayValue(t, uid, `{"schema":"episode-v1","title":"Agenda"}`, 7)
	goDisplay := sealReplayValue(t, uid, `{"schema":"episode-v1","title":"Agenda"}`, 8)
	python.Derived["users/"+uid+"/episodes/e"] = map[string]any{"content": pyContent, "home_display": pyDisplay}
	goRun.Derived["users/"+uid+"/episodes/e"] = map[string]any{"content": goContent, "home_display": goDisplay}

	diffs := compareObservations(python, goRun)
	if hasUnexplained(diffs) || !hasReason(diffs, "transcript_segments") || !hasReason(diffs, "home_display") || !hasReason(diffs, "/content") {
		t.Fatalf("equal plaintext with different nonces was not approved: %+v", diffs)
	}

	mustMap(goRun.Document)["home_display"] = sealReplayValue(t, uid, `{"schema":"home-v1","title":"Different"}`, 9)
	diffs = compareObservations(python, goRun)
	if !hasUnexplainedAt(diffs, "/conversation/home_display") {
		t.Fatalf("different home display plaintext was excused: %+v", diffs)
	}
	mustMap(goRun.Document)["home_display"] = sealReplayValue(t, uid, `{"schema":"home-v1","title":"Agenda"}`, 10)

	goDoc := mustMap(goRun.Derived["users/"+uid+"/episodes/e"])
	goDoc["content"] = sealReplayValue(t, uid, `{"title":"Different","lede":"Review"}`, 11)
	diffs = compareObservations(python, goRun)
	if !hasUnexplainedAt(diffs, "/content") {
		t.Fatalf("different episode content plaintext was excused: %+v", diffs)
	}
	goDoc["content"] = sealReplayValue(t, uid, `{"title":"Agenda","lede":"Review"}`, 12)
	goDoc["home_display"] = sealReplayValue(t, uid, `{"schema":"episode-v1","title":"Different"}`, 13)
	diffs = compareObservations(python, goRun)
	if !hasUnexplainedAt(diffs, "home_display") {
		t.Fatalf("different episode Home plaintext was excused: %+v", diffs)
	}
	goDoc["home_display"] = sealReplayValue(t, uid, `{"schema":"episode-v1","title":"Agenda"}`, 14)

	mustMap(goRun.Document)["transcript_segments"] = "not-an-authenticated-envelope"
	diffs = compareObservations(python, goRun)
	if !hasUnexplainedAt(diffs, "/conversation/transcript_segments") {
		t.Fatalf("undecryptable transcript was excused: %+v", diffs)
	}
}

func TestTranscriptComparisonAcceptsGoDecodedSegmentsAndKeepsStoredFields(t *testing.T) {
	uid := "synthetic-owner"
	python, goRun := ruleRun(), ruleRun()
	python.OwnerID, goRun.OwnerID = uid, uid
	segments := []any{map[string]any{
		"text": "agenda", "start": json.Number("0"), "end": json.Number("1"),
		"speaker": "SPEAKER_00", "speaker_id": json.Number("0"), "speaker_identity_status": "user",
		"speaker_label_source": nil, "speaker_word_seconds": nil, "is_user": true, "original_text": "agenda raw",
	}}
	python.Document = map[string]any{
		"transcript_segments":            encryptedTranscript(t, segments, 41),
		"transcript_segments_compressed": true,
	}
	goRun.Document = map[string]any{"transcript_segments": segments}
	diffs := compareObservations(python, goRun)
	if hasUnexplained(diffs) || !hasReason(diffs, "transcript_segments") {
		t.Fatalf("decoded Go segments did not match encrypted Python transcript: %+v", diffs)
	}
	goSegments := mustSlice(mustMap(goRun.Document)["transcript_segments"])
	mustMap(goSegments[0])["original_text"] = "dropped or changed Python stored field"
	diffs = compareObservations(python, goRun)
	if !hasUnexplainedAt(diffs, "/conversation/transcript_segments") {
		t.Fatalf("changed non-default Python segment field was excused: %+v", diffs)
	}
}

func hasUnexplainedAt(diffs []difference, fragment string) bool {
	for _, diff := range diffs {
		if strings.Contains(diff.Path, fragment) && diff.Reason == "" {
			return true
		}
	}
	return false
}

func TestTranscriptByteWrapperComparesDecodedSegments(t *testing.T) {
	uid := "synthetic-owner"
	segments := []any{map[string]any{
		"text": "byte payload", "start": json.Number("0"), "end": json.Number("1"),
		"speaker": "SPEAKER_00", "is_user": true,
	}}
	plain, err := json.Marshal(segments)
	if err != nil {
		t.Fatal(err)
	}
	var compressed bytes.Buffer
	writer := zlib.NewWriter(&compressed)
	if _, err := writer.Write(plain); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	wrapped := map[string]any{"$bytes": base64.StdEncoding.EncodeToString(compressed.Bytes())}
	py, goRun := ruleRun(), ruleRun()
	py.OwnerID, goRun.OwnerID = uid, uid
	py.Document = map[string]any{"transcript_segments": wrapped, "transcript_segments_compressed": true}
	goRun.Document = map[string]any{
		"transcript_segments": encryptedTranscript(t, segments, 2), "transcript_segments_compressed": true,
	}
	diffs := compareObservations(py, goRun)
	if hasUnexplained(diffs) {
		t.Fatalf("equivalent byte and encrypted transcript payloads differ: %+v", diffs)
	}
}

func TestTranscriptComparesSemanticFieldsAndPreservesNonDefaults(t *testing.T) {
	uid := "synthetic-owner"
	python, goRun := ruleRun(), ruleRun()
	python.OwnerID, goRun.OwnerID = uid, uid
	pySegments := []any{map[string]any{
		"text": "corrected", "start": json.Number("0"), "end": json.Number("1"),
		"speaker": "SPEAKER_00", "is_user": true, "translations": []any{},
		"speech_profile_processed": true, "original_text": "captured",
	}}
	goSegments := []any{map[string]any{
		"text": "corrected", "start": json.Number("0"), "end": json.Number("1"),
		"speaker": "SPEAKER_00", "is_user": true,
	}}
	python.Document = map[string]any{
		"transcript_segments": encryptedTranscript(t, pySegments, 20), "transcript_segments_compressed": true,
	}
	goRun.Document = map[string]any{
		"transcript_segments": encryptedTranscript(t, goSegments, 21), "transcript_segments_compressed": true,
	}
	if diffs := compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/conversation/transcript_segments") {
		t.Fatalf("Go dropping a non-default Python field was excused: %+v", diffs)
	}
	mustMap(goSegments[0])["original_text"] = "captured"
	mustMap(goRun.Document)["transcript_segments"] = encryptedTranscript(t, goSegments, 22)
	if diffs := compareObservations(python, goRun); hasUnexplained(diffs) || !hasReason(diffs, "transcript_segments") {
		t.Fatalf("model defaults prevented equal semantic transcript from matching: %+v", diffs)
	}
	mustMap(goSegments[0])["text"] = "different"
	mustMap(goRun.Document)["transcript_segments"] = encryptedTranscript(t, goSegments, 23)
	if diffs := compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/conversation/transcript_segments") {
		t.Fatalf("different transcript text was excused: %+v", diffs)
	}
}

func TestUserCorrectionsRequireConsistentCompressedStorageAndEqualPlaintext(t *testing.T) {
	uid := "synthetic-owner"
	corrections := []any{map[string]any{"original": "captured", "corrected": "fixed"}}
	python, goRun := ruleRun(), ruleRun()
	python.OwnerID, goRun.OwnerID = uid, uid
	python.Document = map[string]any{
		"data_protection_level": "enhanced", "user_corrections_compressed": true,
		"user_corrections": encryptedCorrections(t, uid, corrections, 31),
	}
	goRun.Document = map[string]any{
		"data_protection_level": "enhanced", "user_corrections_compressed": true,
		"user_corrections": encryptedCorrections(t, uid, corrections, 32),
	}
	if diffs := compareObservations(python, goRun); hasUnexplained(diffs) || !hasReason(diffs, "user_corrections") {
		t.Fatalf("equal corrections with fresh nonces were not approved: %+v", diffs)
	}
	mustMap(goRun.Document)["user_corrections_compressed"] = false
	if diffs := compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/conversation/user_corrections") {
		t.Fatalf("inconsistent correction compression marker was excused: %+v", diffs)
	}
	mustMap(goRun.Document)["user_corrections_compressed"] = true
	mustMap(goRun.Document)["user_corrections"] = encryptedCorrections(
		t, uid, []any{map[string]any{"original": "captured", "corrected": "other"}}, 33,
	)
	if diffs := compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/conversation/user_corrections") {
		t.Fatalf("different correction plaintext was excused: %+v", diffs)
	}

	standard, standardGo := ruleRun(), ruleRun()
	standard.OwnerID, standardGo.OwnerID = uid, uid
	standardBlob := compressedJSON(t, corrections)
	standardGoBlob := compressedJSONLevel(t, corrections, zlib.BestCompression)
	standard.Document = map[string]any{
		"data_protection_level": "standard", "user_corrections_compressed": true,
		"user_corrections": map[string]any{"$bytes": base64.StdEncoding.EncodeToString(standardBlob)},
	}
	standardGo.Document = map[string]any{
		"data_protection_level": "standard", "user_corrections_compressed": true,
		"user_corrections": map[string]any{"$bytes": base64.StdEncoding.EncodeToString(standardGoBlob)},
	}
	if diffs := compareObservations(standard, standardGo); hasUnexplained(diffs) || !hasReason(diffs, "user_corrections") {
		t.Fatalf("standard compressed corrections were not decoded: %+v", diffs)
	}
	mustMap(standardGo.Document)["data_protection_level"] = "enhanced"
	if diffs := compareObservations(standard, standardGo); !hasUnexplainedAt(diffs, "/conversation/user_corrections") {
		t.Fatalf("byte storage inconsistent with enhanced protection was excused: %+v", diffs)
	}
}

func TestEpisodeAttachMemoDifferenceRequiresBothSideChecks(t *testing.T) {
	python, goRun := ruleRun(), ruleRun()
	python.EpisodeAttachMemoValid, goRun.EpisodeAttachMemoValid = true, true
	goRun.EpisodeAttachMemoExpected = true
	path := "users/u/episode_links/c"
	python.Derived[path] = map[string]any{
		"attach_revision": "python-key", "attach_completed": "python-key", "attach_finalized": nil,
	}
	goRun.Derived[path] = map[string]any{
		"attach_revision": "go-key", "attach_completed": "go-key", "attach_finalized": "go-key",
	}
	diffs := compareObservations(python, goRun)
	for _, field := range []string{"attach_revision", "attach_completed", "attach_finalized"} {
		found := false
		for _, diff := range diffs {
			if strings.HasSuffix(diff.Path, "/"+field) && diff.Reason == "attach_memo_cache_fallthrough" {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("valid attach memo checks did not explain %s with cache fall-through: %+v", field, diffs)
		}
	}
	goRun.EpisodeAttachMemoValid = false
	goRun.EpisodeAttachMemoFailureReason = "finalized_binding_mismatch"
	if diffs = compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/go/episode_attach_memo") {
		t.Fatalf("invalid Go memo evidence was excused: %+v", diffs)
	}

	// Equal raw fields are still invalid when Go cannot reproduce its memo key.
	python.Derived[path] = goRun.Derived[path]
	if diffs = compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/go/episode_attach_memo") {
		t.Fatalf("equal invalid Go memo fields escaped validation: %+v", diffs)
	}
}

func TestInvalidGoAttachMemoIsReportedEvenWhenStoredValuesMatchPython(t *testing.T) {
	python, goRun := ruleRun(), ruleRun()
	python.OwnerID, goRun.OwnerID = "u", "u"
	python.ConversationID, goRun.ConversationID = "c", "c"
	python.EpisodeAttachMemoValid = true
	goRun.EpisodeAttachMemoValid = false
	goRun.EpisodeAttachMemoFailureReason = "completed_key_mismatch"
	path := "users/u/episode_links/c"
	link := map[string]any{
		"attach_revision": "same-key", "attach_completed": "same-key",
		"attach_finalized": "same-key", "attach_owner_id": "episode",
	}
	python.Derived[path] = link
	goRun.Derived[path] = map[string]any{
		"attach_revision": "same-key", "attach_completed": "same-key",
		"attach_finalized": "same-key", "attach_owner_id": "episode",
	}

	diffs := compareObservations(python, goRun)
	if !hasKindPath(diffs, "invalid_binding", "/go/derived_documents/users~1u~1episode_links~1c/attach_memo_evidence") {
		t.Fatalf("invalid Go memo evidence was hidden by equal stored values: %+v", diffs)
	}
}

func TestProtectedFieldReasonDoesNotExposePlaintext(t *testing.T) {
	uid := "synthetic-owner"
	left, right := ruleRun(), ruleRun()
	left.OwnerID, right.OwnerID = uid, uid
	left.Document = map[string]any{"home_display": sealReplayValue(t, uid, `{"private":"secret"}`, 1)}
	right.Document = map[string]any{"home_display": sealReplayValue(t, uid, `{"private":"secret"}`, 2)}
	diffs := compareObservations(left, right)
	encoded, err := json.Marshal(diffs)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(encoded, []byte("secret")) || !bytes.Contains(encoded, []byte("fixture key")) {
		t.Fatalf("protected comparison report leaked data or omitted rule evidence: %s", string(encoded))
	}
}

func TestTerminalEpisodeMemoShape(t *testing.T) {
	fields := []string{"attach_revision", "attach_completed", "attach_finalized", "attach_owner_id"}
	for _, cid := range []string{"empty-capture", "transcript-empty-text", unreadableReplayCase} {
		t.Run(cid, func(t *testing.T) {
			python, goRun := ruleRun(), ruleRun()
			path := "users/replay-" + cid + "/episode_links/" + cid
			deadLetter := cid == unreadableReplayCase
			for _, obs := range []*observation{python, goRun} {
				obs.OwnerID, obs.ConversationID = "replay-"+cid, cid
				obs.Document = map[string]any{"episode_id": "episode"}
				link := map[string]any{"episode_id": "episode"}
				obs.Derived[path] = link
				if !deadLetter {
					obs.Status = "discarded"
					mustMap(obs.Document)["discarded"] = true
				}
			}
			if deadLetter {
				python.Status, goRun.Status = "parked", "failure"
				goRun.GoEvidence = map[string]any{"job": map[string]any{"state": "dead_letter", "cause": "conversation_unreadable"}}
			} else {
				// Python's established discard invalidation leaves a null sentinel;
				// the Go terminal link must carry no memo fields at all.
				pythonLink := mustMap(python.Derived[path])
				pythonLink["attach_owner_id"] = "episode"
				for _, field := range fields[:3] {
					pythonLink[field] = nil
				}
			}

			verify := func(t *testing.T, invalidSide string) {
				t.Helper()
				terminalReport, err := compare([]replayCase{{Name: cid, Python: python, Go: goRun}})
				if err != nil {
					t.Fatal(err)
				}
				entry := terminalReport.Cases[0]
				for _, side := range []string{"go", "python"} {
					check := entry.EpisodeAttachMemoChecks[side]
					invalid := side == invalidSide
					if check.Valid == invalid || (check.FailureReason != "") != invalid ||
						hasUnexplainedAt(entry.Differences, "/"+side+"/episode_attach_memo") != invalid {
						t.Fatalf("%s memo check %+v, expected invalid side %q", side, check, invalidSide)
					}
					if invalid && side == "go" && check.FailureReason != "terminal_attach_memo_present" {
						t.Fatalf("unexpected Go terminal memo failure: %+v", check)
					}
				}
				for _, d := range entry.Differences {
					if strings.HasSuffix(d.Path, "/attach_memo_evidence") {
						t.Fatalf("live memo proof was applied to terminal output: %+v", d)
					}
					if episodeAttachMemoField(d.Path, python) && episodeAttachMemoField(d.Path, goRun) {
						t.Fatalf("terminal memo placeholders leaked into value comparison: %+v", d)
					}
				}
			}
			verify(t, "")
			pythonLink := mustMap(python.Derived[path])
			if !deadLetter {
				original := map[string]any{}
				for _, field := range fields {
					if value, present := pythonLink[field]; present {
						original[field] = value
						delete(pythonLink, field)
					}
				}
				verify(t, "") // Python may also represent discarded_without_memo with every field absent.
				for field, value := range original {
					pythonLink[field] = value
				}
			}

			goLink := mustMap(goRun.Derived[path])
			for _, field := range fields {
				for _, value := range []any{nil, "stale"} {
					t.Run("go/"+field+"/present", func(t *testing.T) {
						goLink[field] = value
						verify(t, "go")
						delete(goLink, field)
					})
				}
			}

			if deadLetter {
				for _, field := range fields {
					t.Run("python/"+field+"/present", func(t *testing.T) {
						pythonLink[field] = nil
						verify(t, "python")
						delete(pythonLink, field)
					})
				}
			} else {
				for _, field := range fields {
					original, present := pythonLink[field]
					t.Run("python/"+field+"/invalid", func(t *testing.T) {
						pythonLink[field] = "stale"
						verify(t, "python")
						if present {
							pythonLink[field] = original
						} else {
							delete(pythonLink, field)
						}
					})
				}
			}
		})
	}
}
