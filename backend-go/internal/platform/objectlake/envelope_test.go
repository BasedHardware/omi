package objectlake

import (
	"bytes"
	"compress/zlib"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"testing"
)

// Synthetic cross-language vectors, sealed with Python cryptography AESGCM,
// aes_key_wrap, struct.pack(">4sBI12s", ...) and zlib.compress. The space
// key is bytes(range(32)), the v2 object key is bytes(range(64,96)).
const (
	speechDigest = "66a1e0471693de38ca592fcc66fa8ef0d2f2716d322ec19ca4188442469c4107"
	emptyDigest  = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
	legacy       = "T0xLMQEAAAAHBgYGBgYGBgYGBgYGRMSYR7K/r6DX4WTJfoi3gad+TNMNYFfxsFq/k+SoUanK8HUkaGkYJe5UsLcCuTVSyJMQwt1y4zri5H4QewSxKe0jbCeqMlFf0ocxyzfb9bUy9QEr0aR/9fZZ15fOjLG0Fa4hQIjJ1xa97In6yCDR65bzXgbT5zy0a85bfYosiM+MC0CFOPBa8TjX"
	wrapped      = "T0xLMQIAAAAHBwcHBwcHBwcHBwcHvSonaujHRkx+izlmdKxuDpVYyExgCbP6QTzwameiAII+TXIN8kGfqZjNG2n2MRoqBsGp2Mr17xQT4w/B6RNd0CxyjkeenaEzOaz9hBmAdrfSSjTcR5OBo6N2aI3pgaXJuRffx5kx80/w1LLAsHFXBUwKBexTj6kZOPcbpKM9+2jZVcn2itL0gUZewH5wIM91WD9CT55d+Y9jvtMB2T+a18DqZtFCXCAQsKLggXfU8/XHaA=="
	empty        = "T0xLMQIAAAAHBQUFBQUFBQUFBQUFvSonaujHRkx+izlmdKxuDpVYyExgCbP6QTzwameiAII+TXIN8kGfqZZAc+D/Vg2CJLF4+P7YznA91eifAH7i6zAD"
	prefix       = "test/spaces/owner/transcript/conversation/"
)

func vector(t *testing.T, wire string) (objectRef, []byte) {
	t.Helper()
	b, err := base64.StdEncoding.DecodeString(wire)
	if err != nil {
		t.Fatal(err)
	}
	digest := speechDigest
	if wire == empty {
		digest = emptyDigest
	}
	return objectRef{"test-bucket", prefix + digest, digest, int64(len(b)), 7}, b
}
func fixtureKey() []byte {
	key := make([]byte, 32)
	for i := range key {
		key[i] = byte(i)
	}
	return key
}
func TestPythonEnvelopes(t *testing.T) {
	for _, wire := range []string{legacy, wrapped, empty} {
		ref, b := vector(t, wire)
		got, err := decode(ref, fixtureKey(), b)
		if err != nil || got == nil {
			t.Fatalf("decode: %v", err)
		}
		if wire == empty {
			if len(got) != 0 {
				t.Fatal("expected empty segment list")
			}
			continue
		}
		if len(got) != 2 || string(got[0]) != `{"text":"one"}` || string(got[1]) != `{"speaker":"a","text":"two"}` {
			t.Fatal("segment order, public fields or sidecar filtering changed")
		}
	}
}

func TestPublicSegmentsStripIdentitySuggestions(t *testing.T) {
	got, err := publicSegments([]byte(`[{"text":"one","voice_candidates":[{"person_id":"person-1"}]}]`))
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || string(got[0]) != `{"text":"one"}` {
		t.Fatalf("identity suggestions escaped finalization filtering: %s", got)
	}
}

func TestRejectDamagedEnvelope(t *testing.T) {
	for _, change := range []func(*objectRef, []byte){
		func(_ *objectRef, b []byte) { b[0]++ }, func(_ *objectRef, b []byte) { b[4]++ },
		func(_ *objectRef, b []byte) { b[8]++ }, func(_ *objectRef, b []byte) { b[21]++ },
		func(_ *objectRef, b []byte) { b[len(b)-1]++ }, func(r *objectRef, _ []byte) { r.size++ },
		func(r *objectRef, _ []byte) { r.digest = emptyDigest }, func(r *objectRef, _ []byte) { r.key += "other" },
	} {
		ref, b := vector(t, wrapped)
		change(&ref, b)
		if got, err := decode(ref, fixtureKey(), b); !errors.Is(err, ErrCorrupt) || got != nil {
			t.Fatalf("damaged envelope: %v", err)
		}
	}
}

func TestBoundedSingleCompressedJSONList(t *testing.T) {
	for _, plain := range []string{"not json", "null", "[null]", "[{}]", `[{"text":null}]`, "[] []", strings.Repeat(" ", maxPlain+1)} {
		var buf bytes.Buffer
		z := zlib.NewWriter(&buf)
		if _, err := z.Write([]byte(plain)); err != nil {
			t.Fatal(err)
		}
		if err := z.Close(); err != nil {
			t.Fatal(err)
		}
		if got, err := unpack(buf.Bytes(), fmt.Sprintf("%x", sha256.Sum256([]byte(plain)))); !errors.Is(err, ErrCorrupt) || got != nil {
			t.Fatalf("accepted invalid list of length %d", len(plain))
		}
	}
	var buf bytes.Buffer
	z := zlib.NewWriter(&buf)
	if _, err := z.Write([]byte("[]")); err != nil {
		t.Fatal(err)
	}
	if err := z.Close(); err != nil {
		t.Fatal(err)
	}
	for _, bad := range [][]byte{buf.Bytes()[:buf.Len()-1], append(bytes.Clone(buf.Bytes()), 0)} {
		if _, err := unpack(bad, emptyDigest); !errors.Is(err, ErrCorrupt) {
			t.Fatal("accepted truncated or trailing input")
		}
	}
}
