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
	"fmt"
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
	sealed := append(nonce, aead.Seal(nil, nonce, []byte(plaintext), nil)...)
	return base64.StdEncoding.EncodeToString(sealed)
}

func encryptedTranscript(t *testing.T, uid string, segments any, nonceByte byte) string {
	t.Helper()
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
		"transcript_segments":            encryptedTranscript(t, uid, segments, 1),
		"transcript_segments_compressed": true,
		"home_display":                   sealReplayValue(t, uid, `{"schema":"home-v1","title":"Agenda"}`, 2),
	}
	goRun.Document = map[string]any{
		"transcript_segments":            encryptedTranscript(t, uid, segments, 3),
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

	goRun.Document.(map[string]any)["home_display"] = sealReplayValue(t, uid, `{"schema":"home-v1","title":"Different"}`, 9)
	diffs = compareObservations(python, goRun)
	if !hasUnexplainedAt(diffs, "/conversation/home_display") {
		t.Fatalf("different home display plaintext was excused: %+v", diffs)
	}
	goRun.Document.(map[string]any)["home_display"] = sealReplayValue(t, uid, `{"schema":"home-v1","title":"Agenda"}`, 10)

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

	goRun.Document.(map[string]any)["transcript_segments"] = "not-an-authenticated-envelope"
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
		"transcript_segments":            encryptedTranscript(t, uid, segments, 41),
		"transcript_segments_compressed": true,
	}
	goRun.Document = map[string]any{"transcript_segments": segments}
	diffs := compareObservations(python, goRun)
	if hasUnexplained(diffs) || !hasReason(diffs, "transcript_segments") {
		t.Fatalf("decoded Go segments did not match encrypted Python transcript: %+v", diffs)
	}
	goSegments := mustMap(goRun.Document)["transcript_segments"].([]any)
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
		"transcript_segments": encryptedTranscript(t, uid, segments, 2), "transcript_segments_compressed": true,
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
		"transcript_segments": encryptedTranscript(t, uid, pySegments, 20), "transcript_segments_compressed": true,
	}
	goRun.Document = map[string]any{
		"transcript_segments": encryptedTranscript(t, uid, goSegments, 21), "transcript_segments_compressed": true,
	}
	if diffs := compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/conversation/transcript_segments") {
		t.Fatalf("Go dropping a non-default Python field was excused: %+v", diffs)
	}
	goSegments[0].(map[string]any)["original_text"] = "captured"
	goRun.Document.(map[string]any)["transcript_segments"] = encryptedTranscript(t, uid, goSegments, 22)
	if diffs := compareObservations(python, goRun); hasUnexplained(diffs) || !hasReason(diffs, "transcript_segments") {
		t.Fatalf("model defaults prevented equal semantic transcript from matching: %+v", diffs)
	}
	goSegments[0].(map[string]any)["text"] = "different"
	goRun.Document.(map[string]any)["transcript_segments"] = encryptedTranscript(t, uid, goSegments, 23)
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
	goRun.Document.(map[string]any)["user_corrections_compressed"] = false
	if diffs := compareObservations(python, goRun); !hasUnexplainedAt(diffs, "/conversation/user_corrections") {
		t.Fatalf("inconsistent correction compression marker was excused: %+v", diffs)
	}
	goRun.Document.(map[string]any)["user_corrections_compressed"] = true
	goRun.Document.(map[string]any)["user_corrections"] = encryptedCorrections(
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
	standardGo.Document.(map[string]any)["data_protection_level"] = "enhanced"
	if diffs := compareObservations(standard, standardGo); !hasUnexplainedAt(diffs, "/conversation/user_corrections") {
		t.Fatalf("byte storage inconsistent with enhanced protection was excused: %+v", diffs)
	}
}

func TestEpisodeAttachMemoDifferenceRequiresBothSideChecks(t *testing.T) {
	python, goRun := ruleRun(), ruleRun()
	python.EpisodeAttachMemoValid, goRun.EpisodeAttachMemoValid = true, true
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
	if diffs = compareObservations(python, goRun); !hasUnexplained(diffs) {
		t.Fatalf("invalid Go memo evidence was excused: %+v", diffs)
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
		t.Fatalf("protected comparison report leaked data or omitted rule evidence: %s", fmt.Sprint(encoded))
	}
}
