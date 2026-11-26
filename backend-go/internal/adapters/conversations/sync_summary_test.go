package conversations

import (
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
)

func TestOrdinarySyncSummaryReceipts(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 1, 2, 12, 0, 0, 0, time.UTC)
	minimum := &finalization.NotesMinimum{Reason: "content_below_floor"}
	patch := Finalization{SyncNotesWrittenAt: &now, SyncMinimum: minimum}

	minimumFields := map[string]any{}
	stageSyncSummary(minimumFields, nil, patch)
	if due, ok := minimumFields["summary_due_at"]; !ok || due != nil ||
		minimumFields["summary_blocked_reason"] != "content_below_floor" ||
		minimumFields["summary_processing_lease_until"] != int64(0) || minimumFields["summary_output_present"] != false {
		t.Fatalf("minimum did not waive debt: %v", minimumFields)
	}
	if _, ok := minimumFields["terminal_family"]; ok {
		t.Fatal("terminal family stamped when the Python policy is disabled")
	}
	if _, ok := minimumFields["summary_completed_at"]; ok {
		t.Fatal("minimum completed a rich summary")
	}

	discardFields := map[string]any{"discarded": true}
	stageSyncSummary(discardFields, nil, patch)
	if discardFields["summary_discard_receipted"] != true || discardFields["summary_output_present"] != false {
		t.Fatalf("discard did not retire summary debt: %v", discardFields)
	}

	refresh := map[string]any{"structured.overview": "Refreshed notes"}
	stageSyncSummary(refresh, map[string]any{"summary_completed_at": float64(42)}, patch)
	if _, wrote := refresh["summary_completed_at"]; wrote || refresh["summary_output_present"] != true {
		t.Fatalf("refresh changed the first delivery receipt: %v", refresh)
	}
}
