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
	case len(parts) == 2 && parts[0] == "conversation" && parts[1] == "home_display":
		field = "home_display"
		pyValue, _ = nestedField(python.Document, "home_display")
		goValue, _ = nestedField(goRun.Document, "home_display")
	case len(parts) == 3 && parts[0] == "derived_documents" && parts[2] == "content":
		if !episodeDocumentPath(parts[1]) {
			return ""
		}
		field = "episode content"
		pyValue = derivedField(python, parts[1], "content")
		goValue = derivedField(goRun, parts[1], "content")
	case len(parts) == 3 && parts[0] == "derived_documents" && parts[2] == "home_display":
		if !episodeDocumentPath(parts[1]) {
			return ""
		}
		field = "home_display"
		pyValue = derivedField(python, parts[1], "home_display")
		goValue = derivedField(goRun, parts[1], "home_display")
	default:
		return ""
	}
	pyPlain, pyErr := protectedPlaintext(field, python.OwnerID, pyValue, pyCompressed, defaultReplayTestKey)
	goPlain, goErr := protectedPlaintext(field, goRun.OwnerID, goValue, goCompressed, defaultReplayTestKey)
	if pyErr != nil || goErr != nil || !reflect.DeepEqual(pyPlain, goPlain) {
		return ""
	}
	switch field {
	case "transcript":
		return "both transcript ciphertexts decrypt with the fixture key to the same segment plaintext"
	case "episode content":
		return "both episode content ciphertexts decrypt with the fixture key to the same content plaintext"
	default:
		return "both home_display ciphertexts decrypt with the fixture key to the same card plaintext"
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

func transcriptPlaintext(uid string, value any, compressed bool, key string) ([]byte, error) {
	var content []byte
	switch stored := value.(type) {
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
