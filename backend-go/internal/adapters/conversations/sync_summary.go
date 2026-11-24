package conversations

import (
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
)

// stageSyncSummary records the supported ordinary-sync outcomes in the notes write.
// A banked summary retains its first-delivery receipt.
func stageSyncSummary(fields, row map[string]any, patch Finalization) {
	now := *patch.SyncNotesWrittenAt
	stageTitleReceipt(fields, patch.SyncTitleUpdate, now)
	fields["notes_written_at"] = now
	fields["notes_screen_frame_count"] = int64(0)
	if patch.SyncTerminalFamilyEnabled {
		fields["terminal_family"] = "success"
		fields["terminal_family_at"] = now
	}
	bodies := make([]string, 0)
	if patch.Sections != nil {
		for _, section := range *patch.Sections {
			bodies = append(bodies, section.Body)
		}
	}
	rich := rules.HasSummary(field[string](fields, "structured.overview"), bodies)
	if field[float64](row, "summary_completed_at") > 0 || field[int64](row, "summary_completed_at") > 0 ||
		field[bool](row, "summary_output_present") {
		fields["summary_due_at"] = nil
		if rich {
			fields["summary_output_present"] = true
		}
		return
	}
	discarded := field[bool](fields, "discarded")
	fields["summary_output_present"] = rich
	if discarded && field[bool](row, "summary_discard_receipted") {
		return
	}
	if rich || discarded {
		fields["summary_due_at"] = nil
		fields["summary_processing_lease_until"] = int64(0)
		fields["summary_blocked_reason"] = nil
		fields["summary_discard_receipted"] = discarded && !rich
		if rich {
			fields["summary_completed_at"] = float64(now.UnixMicro()) / 1e6
			fields["summary_title_provenance"] = "generated"
		}
		return
	}
	if patch.SyncMinimum != nil && patch.SyncMinimum.Reason == "content_below_floor" {
		fields["summary_due_at"] = nil
		fields["summary_processing_lease_until"] = int64(0)
		fields["summary_blocked_reason"] = "content_below_floor"
	}
}

func stageTitleReceipt(fields map[string]any, update *finalization.SyncTitleUpdate, now time.Time) {
	if update == nil {
		return
	}
	if update.SetBasis {
		fields["title_content_units"] = update.Basis
	}
	if update.Reason != "" {
		fields["title_change_reason"] = update.Reason
		fields["title_changed_at"] = now
	}
}
