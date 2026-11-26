package finalization

import (
	"encoding/json"
	"testing"
)

func TestSyncOpenLoopExtractionMatchesPythonShape(t *testing.T) {
	t.Parallel()
	raw := `{"delegated_by_user":{"what":" Review the release ","extra":"ignored"},
		"commitments_by_others":[{"by_when":"Friday"},{"who":"Sam","what":"Send the report","work_related":true}],
		"observed_issue_or_blocker":{"kind":"unsupported","what":"Fix this"}}`
	packed, err := json.Marshal(parseSyncOpenLoops(raw))
	if err != nil {
		t.Fatal(err)
	}
	want := `{"version":1,"delegated_by_user":[{"what":"Review the release","by_when":null,"evidence":"","work_related":null,"who":"unknown"}],"commitments_by_others":[{"what":"Send the report","by_when":null,"evidence":"","work_related":true,"who":"Sam"}],"observed_issue_or_blocker":null}`
	if string(packed) != want {
		t.Fatalf("unexpected open loop envelope: %s", packed)
	}
	if loops := parseSyncOpenLoops(`{"title":"Notes"}`); loops == nil || !loops.Empty() {
		t.Fatal("a fresh parse with no open loops must clear old extractions")
	}
}
