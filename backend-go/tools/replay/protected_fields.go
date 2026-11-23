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
	"errors"
	"io"
	"reflect"
	"strconv"
	"strings"
)

const defaultReplayTestKey = "replay-harness-synthetic-encryption-key-0000"

func decryptReplayEnvelope(uid, envelope, secret string) ([]byte, error) {
	sealed, err := base64.StdEncoding.Strict().DecodeString(envelope)
	if err != nil {
		return nil, errors.New("invalid encrypted envelope encoding")
	}
	key, err := hkdf.Key(sha256.New, []byte(secret), []byte(uid), "user-data-encryption", 32)
	if err != nil {
		return nil, err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil || len(sealed) < aead.NonceSize()+aead.Overhead() {
		return nil, errors.New("invalid encrypted envelope")
	}
	return aead.Open(nil, sealed[:aead.NonceSize()], sealed[aead.NonceSize():], nil)
}

func protectedDifferenceReason(path string, python, goRun *observation) string {
	reason, _ := protectedDifferenceEvidence(path, python, goRun)
	return reason
}

func protectedDifferenceEvidence(path string, python, goRun *observation) (string, string) {
	parts := pointerParts(path)
	field := ""
	var pyValue, goValue any
	var pyCompressed, goCompressed bool
	switch {
	case len(parts) >= 2 && parts[0] == "conversation" && parts[1] == "transcript_segments":
		field = "transcript"
		pyValue, _ = nestedField(python.Document, "transcript_segments")
		goValue, _ = nestedField(goRun.Document, "transcript_segments")
		pyCompressed = objectField(python.Document, "transcript_segments_compressed") == true
		goCompressed = objectField(goRun.Document, "transcript_segments_compressed") == true
	case len(parts) == 2 && parts[0] == "conversation" && parts[1] == "transcript_segments_compressed":
		field = "transcript"
		pyValue, _ = nestedField(python.Document, "transcript_segments")
		goValue, _ = nestedField(goRun.Document, "transcript_segments")
		pyCompressed = objectField(python.Document, "transcript_segments_compressed") == true
		goCompressed = objectField(goRun.Document, "transcript_segments_compressed") == true
	case len(parts) >= 2 && parts[0] == "conversation" && parts[1] == "user_corrections":
		field = "user_corrections"
		pyValue, _ = nestedField(python.Document, "user_corrections")
		goValue, _ = nestedField(goRun.Document, "user_corrections")
		pyCompressed = objectField(python.Document, "user_corrections_compressed") == true
		goCompressed = objectField(goRun.Document, "user_corrections_compressed") == true
	case len(parts) == 2 && parts[0] == "conversation" && parts[1] == "user_corrections_compressed":
		field = "user_corrections"
		pyValue, _ = nestedField(python.Document, "user_corrections")
		goValue, _ = nestedField(goRun.Document, "user_corrections")
		pyCompressed = objectField(python.Document, "user_corrections_compressed") == true
		goCompressed = objectField(goRun.Document, "user_corrections_compressed") == true
	case len(parts) == 2 && parts[0] == "conversation" && parts[1] == "home_display":
		field = "home_display"
		pyValue, _ = nestedField(python.Document, "home_display")
		goValue, _ = nestedField(goRun.Document, "home_display")
	case len(parts) == 3 && parts[0] == "derived_documents" && parts[2] == "content":
		if !episodeDocumentPath(parts[1]) {
			return "", ""
		}
		field = "episode content"
		pyValue = derivedField(python, parts[1], "content")
		goValue = derivedField(goRun, parts[1], "content")
	case len(parts) == 3 && parts[0] == "derived_documents" && parts[2] == "home_display":
		if !episodeDocumentPath(parts[1]) {
			return "", ""
		}
		field = "home_display"
		pyValue = derivedField(python, parts[1], "home_display")
		goValue = derivedField(goRun, parts[1], "home_display")
	default:
		return "", ""
	}
	var pyPlain, goPlain any
	var pyErr, goErr error
	if field == "user_corrections" {
		pyPlain, pyErr = correctionsPlaintext(python.OwnerID, pyValue, pyCompressed, objectField(python.Document, "data_protection_level"), defaultReplayTestKey)
		goPlain, goErr = correctionsPlaintext(goRun.OwnerID, goValue, goCompressed, objectField(goRun.Document, "data_protection_level"), defaultReplayTestKey)
	} else {
		pyPlain, pyErr = protectedPlaintext(field, python.OwnerID, pyValue, pyCompressed, defaultReplayTestKey)
		goPlain, goErr = protectedPlaintext(field, goRun.OwnerID, goValue, goCompressed, defaultReplayTestKey)
	}
	if pyErr != nil || goErr != nil {
		if pyErr != nil {
			return "", "python_plaintext_decode_failed"
		}
		return "", "go_plaintext_decode_failed"
	}
	switch field {
	case "transcript":
		if !transcriptSemanticsEqual(pyPlain, goPlain) {
			return "", "transcript_semantics_mismatch"
		}
		if !goPreservesPythonStoredFields(pyPlain, goPlain) {
			return "", "python_stored_segment_field_missing_in_go"
		}
		return "transcript semantic fields match and Go preserves every non-default Python segment field", ""
	case "user_corrections":
		if !reflect.DeepEqual(pyPlain, goPlain) {
			return "", "corrections_plaintext_mismatch"
		}
		return "both correction blobs have storage consistent with their protection level and decrypt to the same correction list", ""
	case "episode content":
		if !reflect.DeepEqual(pyPlain, goPlain) {
			return "", "episode_content_plaintext_mismatch"
		}
		return "both episode content ciphertexts decrypt with the fixture key to the same content plaintext", ""
	default:
		if !reflect.DeepEqual(pyPlain, goPlain) {
			return "", "home_display_plaintext_mismatch"
		}
		return "both home_display ciphertexts decrypt with the fixture key to the same card plaintext", ""
	}
}

func episodeDocumentPath(path string) bool {
	parts := strings.Split(path, "/")
	return len(parts) == 4 && parts[0] == "users" && parts[2] == "episodes"
}

func derivedField(run *observation, docPath, field string) any {
	doc, _ := run.Derived[docPath].(map[string]any)
	return doc[field]
}

func protectedPlaintext(kind, uid string, value any, compressed bool, key string) (any, error) {
	if uid == "" {
		return nil, errors.New("missing replay owner")
	}
	var plaintext []byte
	if kind == "transcript" {
		var err error
		plaintext, err = transcriptPlaintext(uid, value, compressed, key)
		if err != nil {
			return nil, err
		}
	} else {
		encoded, ok := value.(string)
		if !ok || encoded == "" {
			return nil, errors.New("protected blob is not a non-empty ciphertext")
		}
		var err error
		plaintext, err = decryptReplayEnvelope(uid, encoded, key)
		if err != nil {
			return nil, err
		}
	}
	decoder := json.NewDecoder(bytes.NewReader(plaintext))
	decoder.UseNumber()
	var decoded any
	if err := decoder.Decode(&decoded); err != nil {
		return nil, err
	}
	if kind == "transcript" {
		if _, ok := decoded.([]any); !ok {
			return nil, errors.New("transcript plaintext is not a segment list")
		}
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, errors.New("protected plaintext has trailing data")
	}
	return decoded, nil
}

func correctionsPlaintext(uid string, value any, compressed bool, protectionLevel any, key string) (any, error) {
	if uid == "" || !compressed {
		return nil, errors.New("corrections compression marker is missing")
	}
	enhanced, ok := protectionLevel.(string)
	if !ok || (enhanced != "enhanced" && enhanced != "standard") {
		return nil, errors.New("corrections protection level is missing or invalid")
	}
	var payload []byte
	switch stored := value.(type) {
	case string:
		if enhanced != "enhanced" {
			return nil, errors.New("encrypted corrections disagree with protection level")
		}
		decrypted, err := decryptReplayEnvelope(uid, stored, key)
		if err != nil {
			return nil, err
		}
		if strings.ToLower(string(decrypted)) != string(decrypted) {
			return nil, errors.New("corrections compressed hex is not lowercase")
		}
		decoded, err := hex.DecodeString(string(decrypted))
		if err != nil {
			return nil, err
		}
		payload = decoded
	case []byte:
		if enhanced != "standard" {
			return nil, errors.New("plaintext corrections disagree with protection level")
		}
		payload = stored
	case map[string]any:
		if enhanced != "standard" || len(stored) != 1 {
			return nil, errors.New("corrections byte wrapper disagrees with protection level")
		}
		encoded, ok := stored["$bytes"].(string)
		if !ok {
			return nil, errors.New("corrections byte wrapper is malformed")
		}
		decoded, err := base64.StdEncoding.Strict().DecodeString(encoded)
		if err != nil {
			return nil, err
		}
		payload = decoded
	default:
		return nil, errors.New("corrections are not stored as a protected blob")
	}
	reader, err := zlib.NewReader(bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}
	plain, readErr := io.ReadAll(io.LimitReader(reader, 16<<20+1))
	closeErr := reader.Close()
	if readErr != nil || closeErr != nil || len(plain) > 16<<20 {
		return nil, errors.New("invalid compressed corrections")
	}
	decoder := json.NewDecoder(bytes.NewReader(plain))
	decoder.UseNumber()
	var decoded any
	if err := decoder.Decode(&decoded); err != nil {
		return nil, err
	}
	if _, ok := decoded.([]any); !ok {
		return nil, errors.New("corrections plaintext is not a list")
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, errors.New("corrections plaintext has trailing data")
	}
	return decoded, nil
}

func transcriptSemanticsEqual(python, goRun any) bool {
	pySegments, pyOK := python.([]any)
	goSegments, goOK := goRun.([]any)
	if !pyOK || !goOK || len(pySegments) != len(goSegments) {
		return false
	}
	for index := range pySegments {
		py, pyOK := pySegments[index].(map[string]any)
		goSegment, goOK := goSegments[index].(map[string]any)
		if !pyOK || !goOK {
			return false
		}
		for _, field := range []string{"text", "start", "end", "speaker", "is_user"} {
			pyValue, pyPresent := py[field]
			goValue, goPresent := goSegment[field]
			if field == "speaker" {
				if !pyPresent {
					pyValue, pyPresent = "SPEAKER_00", true
				}
				if !goPresent {
					goValue, goPresent = "SPEAKER_00", true
				}
			}
			if !pyPresent || !goPresent || !equalReplayValue(pyValue, goValue) {
				return false
			}
		}
	}
	return true
}

func goPreservesPythonStoredFields(python, goRun any) bool {
	pySegments, pyOK := python.([]any)
	goSegments, goOK := goRun.([]any)
	if !pyOK || !goOK || len(pySegments) != len(goSegments) {
		return false
	}
	for index := range pySegments {
		py, pyOK := pySegments[index].(map[string]any)
		goSegment, goOK := goSegments[index].(map[string]any)
		if !pyOK || !goOK {
			return false
		}
		for field, value := range py {
			if isTranscriptDefault(field, value, py) {
				continue
			}
			goValue, exists := goSegment[field]
			if !exists || !equalReplayValue(value, goValue) {
				return false
			}
		}
	}
	return true
}

func isTranscriptDefault(field string, value any, segment map[string]any) bool {
	defaults := map[string]any{
		"original_text": nil, "speaker": "SPEAKER_00", "person_id": nil,
		"speaker_label_source": nil, "speaker_word_seconds": nil, "translations": []any{},
		"speech_profile_processed": true, "stt_provider": nil, "speaker_match_source": nil,
		"speaker_id_scope": nil, "audio_alignment": nil,
		"audio_capture_run": nil, "audio_capture_start": nil, "audio_capture_end": nil,
		"audio_source": nil, "recurring_voice_id": nil, "voice_candidates": nil,
		"speaker_match_scores": nil, "provider_speaker": nil, "speaker_grouping_shadow": nil,
		"speaker_grouping_shadow_expires_at": nil,
	}
	defaultValue, known := defaults[field]
	if known && reflect.DeepEqual(value, defaultValue) {
		return true
	}
	if field == "speaker_identity_status" {
		expected := "unknown"
		if segment["is_user"] == true {
			expected = "user"
		}
		return value == expected
	}
	if field == "speaker_id" {
		number, ok := value.(json.Number)
		if !ok {
			return false
		}
		actual, err := number.Int64()
		speaker, speakerOK := segment["speaker"].(string)
		if !speakerOK {
			speaker = "SPEAKER_00"
		}
		suffix, found := strings.CutPrefix(speaker, "SPEAKER_")
		expected, parseErr := strconv.ParseInt(suffix, 10, 64)
		return err == nil && found && parseErr == nil && actual == expected
	}
	return false
}

func equalReplayValue(left, right any) bool {
	if a, ok := left.(json.Number); ok {
		if b, ok := right.(json.Number); ok {
			return equalNumbers(a, b)
		}
	}
	return reflect.DeepEqual(left, right)
}

func transcriptPlaintext(uid string, value any, compressed bool, key string) ([]byte, error) {
	var content []byte
	switch stored := value.(type) {
	case []any:
		if compressed {
			return nil, errors.New("decoded transcript segments carry a compression marker")
		}
		encoded, err := json.Marshal(stored)
		if err != nil {
			return nil, err
		}
		content = encoded
	case string:
		plain, err := decryptReplayEnvelope(uid, stored, key)
		if err != nil {
			return nil, err
		}
		content = plain
	case []byte:
		content = stored
	case map[string]any:
		encoded, ok := stored["$bytes"].(string)
		if !ok || len(stored) != 1 {
			return nil, errors.New("transcript byte wrapper is malformed")
		}
		decoded, err := base64.StdEncoding.Strict().DecodeString(encoded)
		if err != nil {
			return nil, err
		}
		content = decoded
	default:
		return nil, errors.New("transcript value is not a ciphertext or byte payload")
	}
	if compressed {
		if _, encrypted := value.(string); encrypted {
			if strings.ToLower(string(content)) != string(content) {
				return nil, errors.New("compressed transcript hex is not lowercase")
			}
			decoded, err := hex.DecodeString(string(content))
			if err != nil {
				return nil, err
			}
			content = decoded
		}
		reader, err := zlib.NewReader(bytes.NewReader(content))
		if err != nil {
			return nil, err
		}
		plain, readErr := io.ReadAll(io.LimitReader(reader, 64<<20+1))
		closeErr := reader.Close()
		if readErr != nil || closeErr != nil || len(plain) > 64<<20 {
			return nil, errors.New("invalid compressed transcript")
		}
		content = plain
	}
	return content, nil
}
