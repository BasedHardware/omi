package finalizationdocs

import (
	"encoding/json"
	"errors"
	"fmt"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestF28SyncContentAndSummaryRearmCommitTogether(t *testing.T) {
	t.Parallel()
	store, bench, req := setup(t)
	a := queue.AdmittingForTest(t, req.Ref.Owner)
	put(t, bench, conversationPath, document{"status": "completed", "data_protection_level": "standard", "summary_blocked_reason": "empty_output_exhausted"})
	for i := range int64(3) {
		snapshot, err := bench.Raw.Doc(conversationPath).Get(t.Context())
		if err != nil {
			t.Fatal(err)
		}
		segments := []json.RawMessage{json.RawMessage(fmt.Sprintf(`{"text":"synthetic speech revision %d"}`, i+1))}
		if revisionErr := store.CommitInlineSyncRevision(t.Context(), a, req.Ref, i, snapshot.UpdateTime, segments); revisionErr != nil {
			t.Fatal(revisionErr)
		}
		row := read(t, bench, conversationPath)
		if row["sync_content_revision"] != i+1 {
			t.Fatal("content revision did not advance")
		}
		if i == 2 {
			if row["summary_blocked_reason"] != "empty_output_lifetime_exhausted" || row["summary_due_at"] != nil {
				t.Fatal("third revision escaped the empty-output cap")
			}
		} else {
			if row["summary_empty_rearms"] != i+1 || row["summary_blocked_reason"] != nil || row["summary_due_at"] == nil {
				t.Fatal("new content did not atomically restore one debt budget")
			}
			row["summary_blocked_reason"] = "empty_output_exhausted"
			put(t, bench, conversationPath, row)
		}
		if staleErr := store.CommitInlineSyncRevision(t.Context(), a, req.Ref, i, snapshot.UpdateTime, segments); !errors.Is(staleErr, finalization.ErrStale) {
			t.Fatalf("old sync writer changed debt: %v", staleErr)
		}
	}
}
