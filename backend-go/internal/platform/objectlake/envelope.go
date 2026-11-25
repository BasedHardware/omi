package objectlake

import (
	"bytes"
	"compress/zlib"
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"unicode/utf8"

	josecipher "github.com/go-jose/go-jose/v4/cipher"
)

func decode(ref objectRef, spaceKey, payload []byte) ([]json.RawMessage, error) {
	const header = 21 // magic, format, space-key version, 96-bit nonce
	if int64(len(payload)) != ref.size || len(payload) < header+16 || string(payload[:4]) != "OLK1" || int64(binary.BigEndian.Uint32(payload[5:9])) != ref.version {
		return nil, ErrCorrupt
	}
	block, err := aes.NewCipher(spaceKey)
	if err != nil {
		return nil, ErrUnavailable
	}
	offset := header
	switch payload[4] {
	case 1:
	case 2:
		offset += 40 // RFC 3394 wrapping of a 32-byte object key
		if len(payload) < offset+16 {
			return nil, ErrCorrupt
		}
		dek, unwrapErr := josecipher.KeyUnwrap(block, payload[header:offset])
		if unwrapErr != nil {
			return nil, ErrCorrupt
		}
		block, err = aes.NewCipher(dek)
		clear(dek)
		if err != nil {
			return nil, ErrCorrupt
		}
	default:
		return nil, ErrCorrupt
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, ErrCorrupt
	}
	compressed, err := aead.Open(nil, payload[9:header], payload[offset:], []byte(ref.key))
	if err != nil {
		return nil, ErrCorrupt
	}
	defer clear(compressed)
	return unpack(compressed, ref.digest)
}

func unpack(compressed []byte, digest string) ([]json.RawMessage, error) {
	input := bytes.NewReader(compressed)
	stream, err := zlib.NewReader(input)
	if err != nil {
		return nil, ErrCorrupt
	}
	plain, readErr := io.ReadAll(io.LimitReader(stream, maxPlain+1))
	defer clear(plain)
	if errors.Join(readErr, stream.Close()) != nil || len(plain) > maxPlain || input.Len() != 0 {
		return nil, ErrCorrupt
	}
	sum := sha256.Sum256(plain)
	if hex.EncodeToString(sum[:]) != digest || !utf8.Valid(plain) || !json.Valid(plain) {
		return nil, ErrCorrupt
	}
	return publicSegments(plain)
}

func publicSegments(plain []byte) ([]json.RawMessage, error) {
	decoder := json.NewDecoder(bytes.NewReader(plain))
	tok, err := decoder.Token()
	if err != nil || tok != json.Delim('[') {
		return nil, ErrCorrupt
	}
	segments := []json.RawMessage{}
	for decoder.More() {
		var fields map[string]json.RawMessage
		if err = decoder.Decode(&fields); err != nil {
			return nil, ErrCorrupt
		}
		// A valid JSON string starts with a quote. The decoder validated the field.
		if text := fields["text"]; len(text) == 0 || text[0] != '"' {
			return nil, ErrCorrupt
		}
		for _, name := range []string{"recurring_voice_id", "speaker_grouping_internal", "provider_speaker", "speaker_grouping_shadow", "speaker_grouping_shadow_expires_at", "voice_candidates"} {
			delete(fields, name)
		}
		segment, err := json.Marshal(fields)
		if err != nil {
			return nil, ErrCorrupt
		}
		segments = append(segments, segment)
	}
	return segments, nil
}
