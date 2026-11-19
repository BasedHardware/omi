package crypt

import (
	"bytes"
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

func TestTranscriptFormatsRoundTrip(t *testing.T) {
	c := New("example secret with Unicode \u03bb")
	raw := []byte(`[{"text":"a ñ","start":0},{"text":"雪","speaker":"p"}]`)
	for _, format := range []string{"standard_list", "standard_zlib", "enhanced_json", "enhanced_zlib"} {
		t.Run(format, func(t *testing.T) {
			storage, err := c.Encode("owner", Format(format), raw, nil)
			if err != nil {
				t.Fatal(err)
			}
			list, err := c.Decode("owner", storage)
			if err != nil {
				t.Fatal(err)
			}
			text, err := c.DecodeText("owner", storage)
			if err != nil || text != "a ñ 雪" {
				t.Fatalf("decode = %q, %v", text, err)
			}
			got, err := json.Marshal(list)
			if err != nil || !bytes.Equal(got, raw) {
				t.Fatalf("segments changed: %v", err)
			}
			if strings.HasPrefix(format, "enhanced") {
				if _, err := c.Decode("someone else", storage); !errors.Is(err, ErrUnreadable) {
					t.Fatalf("wrong tenant: %v", err)
				}
			}
		})
	}
}

func TestUnreadableTranscript(t *testing.T) {
	c := New("sample")
	for _, tc := range []Transcript{
		{},
		{[]byte(`null`), false},
		{[]byte(`[{"text":null}]`), false},
		{[]byte(`[{"text":false}]`), false},
		{[]byte(`"invalid ciphertext"`), false},
		{[]byte(`{"base64":"AAAA"}`), true},
	} {
		if _, err := c.Decode("owner", tc); !errors.Is(err, ErrUnreadable) {
			t.Fatalf("accepted unreadable segment: %v", err)
		}
	}
}
