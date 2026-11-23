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

func TestProtectedFieldsAllowDifferentNoncesOnlyForEqualPlaintext(t *testing.T) {
	uid := "synthetic-owner"
	python, goRun := ruleRun(), ruleRun()
	python.OwnerID, goRun.OwnerID = uid, uid
	python.Document = map[string]any{
		"transcript_segments":            encryptedTranscript(t, uid, []any{map[string]any{"text": "agenda"}}, 1),
		"transcript_segments_compressed": true,
		"home_display":                   sealReplayValue(t, uid, `{"schema":"home-v1","title":"Agenda"}`, 2),
	}
	goRun.Document = map[string]any{
		"transcript_segments":            encryptedTranscript(t, uid, []any{map[string]any{"text": "agenda"}}, 3),
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
	segments := []any{map[string]any{"text": "byte payload"}}
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
