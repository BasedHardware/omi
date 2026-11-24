package conversations

import (
	"encoding/json"
	"slices"
	"testing"
)

func TestRecordingSpeakerScopesUsesUniqueSortedScopes(t *testing.T) {
	t.Parallel()
	scopes, err := RecordingSpeakerScopes([]json.RawMessage{
		json.RawMessage(`{"speaker_id_scope":"stream:2"}`),
		json.RawMessage(`{"speaker_id_scope":"stream:1"}`),
		json.RawMessage(`{"speaker_id_scope":"stream:2"}`),
		json.RawMessage(`{"speaker_id_scope":null}`),
		json.RawMessage(`{}`),
	})
	if err != nil || !slices.Equal(scopes, []string{"stream:1", "stream:2"}) {
		t.Fatalf("scope index = %v, %v", scopes, err)
	}
	empty, err := RecordingSpeakerScopes(nil)
	if err != nil || empty == nil || len(empty) != 0 {
		t.Fatalf("scope index for empty case = %#v, %v", empty, err)
	}
}
