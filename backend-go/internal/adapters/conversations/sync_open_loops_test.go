package conversations

import (
	"bytes"
	"compress/zlib"
	"encoding/hex"
	"encoding/json"
	"io"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
)

func TestOpenLoopWriteProtection(t *testing.T) {
	t.Parallel()
	const owner = "synthetic-owner"
	const payload = `{"version":1,"delegated_by_user":[],"commitments_by_others":[],"observed_issue_or_blocker":{"what":"File regression","by_when":null,"evidence":"","work_related":null,"kind":"work_defect"}}`
	var loops finalization.SyncOpenLoops
	if err := json.Unmarshal([]byte(payload), &loops); err != nil {
		t.Fatal(err)
	}
	s := Store{Codec: crypt.New("synthetic conversations test key")}
	fields := make(map[string]any)
	if err := s.stageSyncFields(owner, fields, nil, Finalization{SyncOpenLoops: &loops}); err != nil {
		t.Fatal(err)
	}
	sealed, ok := fields["open_loop_extractions"].(string)
	if !ok || fields["open_loop_extractions_compressed"] != true {
		t.Fatal("missing protection setting must use enhanced storage")
	}
	encoded, err := s.Codec.Open(owner, sealed)
	if err != nil {
		t.Fatal(err)
	}
	compressed, err := hex.DecodeString(string(encoded))
	if err != nil {
		t.Fatal(err)
	}
	reader, err := zlib.NewReader(bytes.NewReader(compressed))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if closeErr := reader.Close(); closeErr != nil {
			t.Error(closeErr)
		}
	}()
	decoded, err := io.ReadAll(reader)
	if err != nil || string(decoded) != payload {
		t.Fatalf("incorrect enhanced derived blob: %v", err)
	}

	cleared := make(map[string]any)
	if stageErr := s.stageSyncFields(owner, cleared, nil, Finalization{SyncOpenLoops: &finalization.SyncOpenLoops{}}); stageErr != nil {
		t.Fatal(stageErr)
	}
	for _, field := range []string{"open_loop_extractions", "open_loop_extractions_compressed"} {
		if value, present := cleared[field]; !present || value != nil {
			t.Fatalf("empty fresh extraction must clear %s", field)
		}
	}
}
