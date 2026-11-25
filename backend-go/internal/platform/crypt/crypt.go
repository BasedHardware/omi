// Package crypt reads and writes Omi's at-rest encryption and its stored transcript formats.
//
// It must stay compatible in both directions with the Python backend
// (backend/utils/encryption.py and the transcript codec in backend/database): this package
// reads what Python wrote, and Python reads what this package writes. The conformance kit
// checks both directions against the real Python module.
//
// Unlike the Python reader, a failed decryption here is always an error. It never returns the
// ciphertext as if it were text.
//
// Not supported yet: a transcript the Python backend moved to the object lake, which is
// stored as a pointer document instead of the text. This package reports it as ErrUnreadable.
// The conversation family that first reads such transcripts adds the pointer reader.
package crypt

import (
	"bytes"
	"compress/zlib"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hkdf"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
)

// ErrUnreadable means stored data could not be decrypted or decoded. It carries no detail,
// so it is safe to log and to return to a caller.
var ErrUnreadable = errors.New("transcript_unreadable")

// MinSecretBytes is the shortest deployment secret the Python backend accepts.
const MinSecretBytes = 32

// ErrWeakSecret means the deployment secret is shorter than MinSecretBytes.
var ErrWeakSecret = errors.New("crypt: deployment secret is shorter than 32 bytes")

// Check reports whether secret is one the Python backend would also accept. A binary calls
// it once at start-up, before it serves anything.
func Check(secret string) error {
	if len(secret) < MinSecretBytes {
		return ErrWeakSecret
	}
	return nil
}

const (
	keyInfo       = "user-data-encryption"
	keyLength     = 32
	maxTranscript = 64 << 20
)

// Codec seals and opens data for users under one deployment secret.
type Codec struct{ secret []byte }

// New returns a codec for the deployment secret, used as raw UTF-8 bytes as Python does.
func New(secret string) Codec { return Codec{[]byte(secret)} }

// aead derives the user's key: HKDF-SHA256 over the secret, salted with the user id.
func (c Codec) aead(uid string) (cipher.AEAD, error) {
	key, err := hkdf.Key(sha256.New, c.secret, []byte(uid), keyInfo, keyLength)
	if err != nil {
		return nil, fmt.Errorf("derive key: %w", err)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("cipher: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm: %w", err)
	}
	return gcm, nil
}

// Seal encrypts plaintext for a user with a fresh random nonce. The envelope is standard
// padded base64 of nonce, ciphertext and tag. An empty plaintext is stored as an empty string.
func (c Codec) Seal(uid string, plaintext []byte) (string, error) {
	return c.SealWithNonce(uid, plaintext, nil)
}

// SealWithNonce is Seal with a caller-chosen nonce. It exists only to reproduce known-answer
// vectors; production code calls Seal, because reusing a nonce under one key breaks the cipher.
func (c Codec) SealWithNonce(uid string, plaintext, nonce []byte) (string, error) {
	if len(plaintext) == 0 {
		return "", nil
	}
	aead, err := c.aead(uid)
	if err != nil {
		return "", err
	}
	if nonce == nil {
		nonce = make([]byte, aead.NonceSize())
		if _, err := rand.Read(nonce); err != nil {
			return "", fmt.Errorf("nonce: %w", err)
		}
	}
	if len(nonce) != aead.NonceSize() {
		return "", ErrUnreadable
	}
	sealed := aead.Seal(append([]byte(nil), nonce...), nonce, plaintext, nil)
	return base64.StdEncoding.EncodeToString(sealed), nil
}

// Open decrypts an envelope for a user. An empty envelope is empty plaintext.
func (c Codec) Open(uid, envelope string) ([]byte, error) {
	if envelope == "" {
		return []byte{}, nil
	}
	aead, err := c.aead(uid)
	if err != nil {
		return nil, ErrUnreadable
	}
	raw, err := base64.StdEncoding.Strict().DecodeString(envelope)
	if err != nil || len(raw) < aead.NonceSize()+aead.Overhead() {
		return nil, ErrUnreadable
	}
	plaintext, err := aead.Open(nil, raw[:aead.NonceSize()], raw[aead.NonceSize():], nil)
	if err != nil {
		return nil, ErrUnreadable
	}
	return plaintext, nil
}

// Transcript is a conversation's stored transcript: the two fields a document carries.
type Transcript struct {
	Segments   json.RawMessage `json:"transcript_segments"`
	Compressed bool            `json:"transcript_segments_compressed"`
}

// Format is one of the four ways a transcript is stored. The set is closed.
type Format string

// The stored transcript formats.
const (
	// FormatStandardList is a plain JSON list of segments (legacy, standard protection).
	FormatStandardList Format = "standard_list"
	// FormatStandardZlib is zlib-compressed JSON carried as bytes (standard protection).
	FormatStandardZlib Format = "standard_zlib"
	// FormatEnhancedJSON is sealed JSON (legacy, enhanced protection).
	FormatEnhancedJSON Format = "enhanced_json"
	// FormatEnhancedZlib is sealed lowercase hex of zlib-compressed JSON (enhanced protection).
	FormatEnhancedZlib Format = "enhanced_zlib"
)

// bytesValue is how the conformance wire carries a bytes field.
type bytesValue struct {
	Base64 string `json:"base64"`
}

type segment struct {
	Text *string `json:"text"`
}

// plain returns the transcript's JSON, whichever format it is stored in.
func (c Codec) plain(uid string, t Transcript) ([]byte, error) {
	raw := bytes.TrimSpace(t.Segments)
	if len(raw) == 0 {
		return nil, ErrUnreadable
	}
	var err error
	switch raw[0] {
	case '{':
		if t.Compressed {
			raw, err = unwrapBytes(raw)
		}
	case '"':
		raw, err = c.unseal(uid, raw, t.Compressed)
	}
	if err != nil {
		return nil, err
	}
	if !t.Compressed {
		return raw, nil
	}
	return inflate(raw)
}

func unwrapBytes(raw []byte) ([]byte, error) {
	var payload bytesValue
	if json.Unmarshal(raw, &payload) != nil {
		return nil, ErrUnreadable
	}
	data, err := base64.StdEncoding.Strict().DecodeString(payload.Base64)
	if err != nil {
		return nil, ErrUnreadable
	}
	return data, nil
}

// unseal opens a sealed transcript string. When compressed, the plaintext is lowercase hex.
func (c Codec) unseal(uid string, raw []byte, compressed bool) ([]byte, error) {
	var envelope string
	if json.Unmarshal(raw, &envelope) != nil {
		return nil, ErrUnreadable
	}
	opened, err := c.Open(uid, envelope)
	if err != nil || !compressed {
		return opened, err
	}
	if strings.ToLower(string(opened)) != string(opened) {
		return nil, ErrUnreadable
	}
	data, err := hex.DecodeString(string(opened))
	if err != nil {
		return nil, ErrUnreadable
	}
	return data, nil
}

func inflate(data []byte) ([]byte, error) {
	z, err := zlib.NewReader(bytes.NewReader(data))
	if err != nil {
		return nil, ErrUnreadable
	}
	raw, err := io.ReadAll(io.LimitReader(z, maxTranscript+1))
	if closeErr := z.Close(); err != nil || closeErr != nil || len(raw) > maxTranscript {
		return nil, ErrUnreadable
	}
	return raw, nil
}

// Decode returns the transcript's segments as stored, after checking that each has text.
func (c Codec) Decode(uid string, t Transcript) ([]json.RawMessage, error) {
	raw, err := c.plain(uid, t)
	if err != nil {
		return nil, err
	}
	return segments(raw)
}

// DecodeText returns the transcript as one string: every segment's text, in stored order,
// joined by single spaces. Empty segments are kept, so the result is exactly the vendor input.
func (c Codec) DecodeText(uid string, t Transcript) (string, error) {
	raw, err := c.plain(uid, t)
	if err != nil {
		return "", err
	}
	var list []segment
	if json.Unmarshal(raw, &list) != nil || list == nil {
		return "", ErrUnreadable
	}
	text := make([]string, len(list))
	for i, s := range list {
		if s.Text == nil {
			return "", ErrUnreadable
		}
		text[i] = *s.Text
	}
	return strings.Join(text, " "), nil
}

func segments(raw []byte) ([]json.RawMessage, error) {
	var list []json.RawMessage
	if err := json.Unmarshal(raw, &list); err != nil || list == nil {
		return nil, ErrUnreadable
	}
	for _, item := range list {
		var s segment
		if json.Unmarshal(item, &s) != nil || s.Text == nil {
			return nil, ErrUnreadable
		}
	}
	return list, nil
}

// Encode stores a JSON list of segments in the given format. nonce is nil in production; a
// fixed nonce reproduces known-answer vectors (see SealWithNonce).
func (c Codec) Encode(uid string, format Format, raw, nonce []byte) (Transcript, error) {
	list, err := segments(raw)
	if err != nil {
		return Transcript{}, err
	}
	canonical, err := json.Marshal(list)
	if err != nil {
		return Transcript{}, ErrUnreadable
	}
	switch format {
	case FormatStandardList:
		return Transcript{Segments: canonical}, nil
	case FormatEnhancedJSON:
		return c.sealed(uid, canonical, nonce, false)
	case FormatStandardZlib:
		deflated, err := deflate(canonical)
		if err != nil {
			return Transcript{}, err
		}
		wrapped, err := json.Marshal(bytesValue{base64.StdEncoding.EncodeToString(deflated)})
		if err != nil {
			return Transcript{}, ErrUnreadable
		}
		return Transcript{Segments: wrapped, Compressed: true}, nil
	case FormatEnhancedZlib:
		deflated, err := deflate(canonical)
		if err != nil {
			return Transcript{}, err
		}
		return c.sealed(uid, []byte(hex.EncodeToString(deflated)), nonce, true)
	}
	return Transcript{}, ErrUnreadable
}

func deflate(raw []byte) ([]byte, error) {
	var out bytes.Buffer
	z := zlib.NewWriter(&out)
	if _, err := z.Write(raw); err != nil {
		return nil, fmt.Errorf("deflate: %w", err)
	}
	if err := z.Close(); err != nil {
		return nil, fmt.Errorf("deflate: %w", err)
	}
	return out.Bytes(), nil
}

func (c Codec) sealed(uid string, raw, nonce []byte, compressed bool) (Transcript, error) {
	envelope, err := c.SealWithNonce(uid, raw, nonce)
	if err != nil {
		return Transcript{}, err
	}
	payload, err := json.Marshal(envelope)
	if err != nil {
		return Transcript{}, ErrUnreadable
	}
	return Transcript{Segments: payload, Compressed: compressed}, nil
}

// UpgradeJSON moves retained standard JSON to the canonical enhanced zlib
// representation. An unreadable blob cannot be omitted during an upgrade.
func (c Codec) UpgradeJSON(uid string, value any, compressed bool, prefix byte) (string, error) {
	raw, err := standardJSON(value, compressed)
	if err != nil {
		return "", err
	}
	raw = bytes.TrimSpace(raw)
	if len(raw) == 0 || len(raw) > maxTranscript || raw[0] != prefix || !json.Valid(raw) {
		return "", ErrUnreadable
	}
	deflated, err := deflate(raw)
	if err != nil {
		return "", err
	}
	return c.Seal(uid, []byte(hex.EncodeToString(deflated)))
}

func standardJSON(value any, compressed bool) ([]byte, error) {
	switch raw := value.(type) {
	case []byte:
		if compressed {
			return inflate(raw)
		}
		return raw, nil
	case []any, map[string]any:
		// Legacy standard rows can still contain an uncompressed JSON value.
		if !compressed {
			return json.Marshal(raw)
		}
	}
	return nil, ErrUnreadable
}
