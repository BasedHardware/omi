package conversations_test

import (
	"bytes"
	"compress/zlib"
	"encoding/hex"
	"errors"
	"io"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
)

const correctionsField = "user_corrections"
const correctionsFlag = "user_corrections_compressed"

func readCorrections(t *testing.T, stored any) string {
	t.Helper()
	var compressed []byte
	switch value := stored.(type) {
	case []byte:
		compressed = value
	case string:
		plaintext, err := crypt.New(key).Open(owner, value)
		if err != nil {
			t.Fatal(err)
		}
		compressed, err = hex.DecodeString(string(plaintext))
		if err != nil {
			t.Fatal(err)
		}
	default:
		t.Fatalf("unexpected stored corrections type %T", value)
	}
	reader, err := zlib.NewReader(bytes.NewReader(compressed))
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := io.ReadAll(reader)
	closeErr := reader.Close()
	if closeErr != nil {
		t.Fatal(closeErr)
	}
	if err != nil {
		t.Fatal(err)
	}
	return string(decoded)
}

func TestSyncFinalizationRetainsCorrectionsAndMatchesStorageProtection(t *testing.T) {
	t.Parallel()
	for _, level := range []string{"standard", "enhanced"} {
		t.Run(level, func(t *testing.T) {
			t.Parallel()
			b, s, g := open(t)
			patch := conversations.Finalization{Status: new(conversations.Completed), SyncFieldMask: true}
			clauses := []any{map[string]any{"text": "owner correction", "evidence": []any{"sample"}}}
			ref := seed(t, b, "corrected", map[string]any{
				"status": "processing", "data_protection_level": level, correctionsField: clauses,
				"home_content_invalidated": true,
			})
			before, err := s.Load(t.Context(), g, ref)
			if err != nil {
				t.Fatal(err)
			}
			edited := read(t, b, ref)
			edited[correctionsField] = []any{map[string]any{"text": "latest owner correction", "evidence": []any{"sample"}}}
			seed(t, b, ref.ID, edited)
			if staleErr := s.ApplyFinalization(t.Context(), g, before.Revision, patch); !errors.Is(staleErr, conversations.ErrChanged) {
				t.Fatalf("stale corrections write = %v", staleErr)
			}
			before, err = s.Load(t.Context(), g, ref)
			if err != nil {
				t.Fatal(err)
			}
			if applyErr := s.ApplyFinalization(t.Context(), g, before.Revision, patch); applyErr != nil {
				t.Fatal(applyErr)
			}
			row := read(t, b, ref)
			_, sealed := row[correctionsField].(string)
			if sealed != (level == "enhanced") || row[correctionsFlag] != true {
				t.Fatalf("wrong corrections representation for %s", level)
			}
			if got := readCorrections(t, row[correctionsField]); got != `[{"evidence":["sample"],"text":"latest owner correction"}]` {
				t.Fatalf("corrections = %s", got)
			}
			if row["home_content_invalidated"] != true {
				t.Fatal("status-only finalization cleared the Home invalidation")
			}

			before, err = s.Load(t.Context(), g, ref)
			if err != nil {
				t.Fatal(err)
			}
			patch.Title = new("Updated notes")
			patch.Overview = new("Includes the latest owner correction")
			patch.Sections = &[]finalization.NoteSection{}
			if applyErr := s.ApplyFinalization(t.Context(), g, before.Revision, patch); applyErr != nil {
				t.Fatal(applyErr)
			}
			updated := read(t, b, ref)
			assertJSON(t, updated[correctionsField], row[correctionsField])
			if updated["home_content_invalidated"] != false {
				t.Fatal("fresh sync notes did not clear the Home invalidation")
			}
		})
	}
}

func TestSyncFinalizationMaterializesMissingCorrections(t *testing.T) {
	t.Parallel()
	b, s, g := open(t)
	ref := seed(t, b, "no-corrections", map[string]any{"status": "processing", "data_protection_level": "standard"})
	before, err := s.Load(t.Context(), g, ref)
	if err != nil {
		t.Fatal(err)
	}
	patch := conversations.Finalization{Status: new(conversations.Completed), SyncFieldMask: true}
	if applyErr := s.ApplyFinalization(t.Context(), g, before.Revision, patch); applyErr != nil {
		t.Fatal(applyErr)
	}
	row := read(t, b, ref)
	if row[correctionsFlag] != true || readCorrections(t, row[correctionsField]) != "[]" {
		t.Fatal("missing corrections did not materialize as an empty protected list")
	}
}
