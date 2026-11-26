package conversations

import (
	"strings"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
)

// finalizerMinimum recognizes summary debt on an otherwise completed row
// that is still bound to the caller's job. The service verifies that binding
// before consulting this snapshot.
func finalizerMinimum(row, structured map[string]any, sections []finalization.NoteSection) bool {
	if field[string](row, "finalization_job_id") == "" {
		return false
	}
	bodies := make([]string, 0, len(sections))
	for _, section := range sections {
		bodies = append(bodies, section.Body)
	}
	block := field[string](row, "summary_blocked_reason")
	decision := field[map[string]any](row, "relevance_decision")
	level := field[string](row, "data_protection_level")
	return rules.CanRepairSummary(rules.SummaryDebt{
		Complete:  field[string](row, "status") == string(Completed),
		Deleted:   field[bool](row, "deleted") || field[bool](row, "is_deleted") || field[string](row, "sync_merged_into") != "",
		Discarded: field[bool](row, "discarded"),
		LocalOnly: field[bool](row, "deferred") || field[bool](row, "is_locked") ||
			field[bool](row, "terminal_no_derived_effects") || field[string](row, "processing_state") == "local_pending" ||
			len(field[map[string]any](row, "client_processing")) > 0,
		Protected: level != "" && level != "standard" && level != "enhanced",
		Manual:    row["user_title"] != nil || row["user_overview"] != nil,
		IntentionalShort: field[string](structured, "title_provenance") == "server_minimum" &&
			field[string](decision, "verdict") == "keep" && field[string](decision, "decided_by") == "rule" &&
			field[string](decision, "reason") == "content_below_floor",
		ServerMinimum: field[string](row, "summary_title_provenance") == "server_minimum",
		HasSummary: row["summary_completed_at"] != nil || field[bool](row, "summary_output_present") ||
			rules.HasSummary(field[string](structured, "overview"), bodies),
		EmptyBlocked: block == "empty_output_exhausted" || block == "empty_output_lifetime_exhausted",
		FinalizerOwns: field[string](row, "finalization_status") == string(BlockedBYOK) ||
			strings.Contains(field[string](row, "finalization_job_id"), "/"),
	})
}
