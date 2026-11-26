package conversations

import (
	"strings"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

func finalizationFields(row map[string]any, patch Finalization) (map[string]any, bool) {
	refused := refusesLifecycle(row, patch)
	if refused && patch.SyncMinimum != nil {
		return nil, true
	}
	if refused {
		patch.Status = nil
		patch.FinalizationStatus = nil
		patch.Discarded = nil
	}
	fields := make(map[string]any)
	if patch.Status != nil {
		fields["status"] = string(*patch.Status)
	}
	if patch.FinalizationStatus != nil {
		fields["finalization_status"] = string(*patch.FinalizationStatus)
	}
	if patch.Discarded != nil {
		fields["discarded"] = effectiveDiscard(row, *patch.Discarded)
	}
	if patch.FinishedAt != nil {
		fields["finished_at"] = patch.FinishedAt.UTC()
	}
	if patch.SummaryCoversThrough != nil {
		fields["summary_covers_through"] = patch.SummaryCoversThrough.UTC()
	}
	if patch.Title != nil {
		title := *patch.Title
		if field[bool](row, "title_locked") {
			title = field[string](field[map[string]any](row, "structured"), "title")
		}
		fields["structured.title"] = effectiveTitle(row, title)
	}
	if patch.Overview != nil {
		fields["structured.overview"] = effectiveOverview(row, *patch.Overview)
	}
	structured := field[map[string]any](row, "structured")
	stageNotesFields(fields, patch, structured)
	if !refused {
		stageServingSyncFields(fields, row, structured, patch)
		if source := patch.SyncSourceProjection; source != nil {
			stageSyncSource(fields, row, patch, source)
		}
	}
	if minimum := patch.SyncMinimum; minimum != nil {
		stageSyncMinimumFields(fields, row, *minimum)
		stageEmptyDiscardProjection(fields, row, patch, *minimum)
	}
	if !refused && patch.InlineFanoutEpoch > 0 {
		stageInlineFanout(fields, row, patch.InlineFanoutEpoch)
	}
	if !refused && patch.SyncNotesWrittenAt != nil {
		stageSyncSummary(fields, row, patch)
	}
	return fields, refused
}

func stageInlineFanout(fields, row map[string]any, epoch int64) {
	fields["go_sync_inline_fanout_epoch"] = epoch
	fields["go_sync_inline_fanout_revision"] = field[int64](row, "sync_content_revision")
}

func stageEmptyDiscardProjection(fields, row map[string]any, patch Finalization, minimum finalization.NotesMinimum) {
	source := patch.SyncSourceProjection
	if source == nil || !minimum.EmptyTranscriptDiscard() || !field[bool](fields, "discarded") {
		return
	}
	stageEmptyDiscardHome(fields, row, source.EmptyDiscardHome)
	if patch.EmptyDiscardFanoutEpoch > 0 {
		fields[finalization.EmptyDiscardFanoutEpochField] = patch.EmptyDiscardFanoutEpoch
	}
}

func stageEmptyDiscardHome(fields, row map[string]any, card *finalization.SyncDiscardHome) {
	if card == nil || card.Display == "" || card.Version == "" || card.SortAt.IsZero() || card.Schema != 1 {
		return
	}
	fields["home_display"] = card.Display
	fields["home_display_version"] = card.Version
	fields["home_sort_at"] = card.SortAt
	fields["home_started_at"] = card.StartedAt
	fields["home_projection_schema"] = card.Schema
	fields["home_has_tasks"] = card.HasTasks
	fields["go_sync_empty_discard_home_revision"] = field[int64](row, "sync_content_revision")
}

func stageSyncSource(fields, row map[string]any, patch Finalization, source *finalization.SyncSourceProjection) {
	fields["recorded_start"] = source.RecordedStart
	fields["recorded_end"] = source.RecordedEnd
	fields["arrival_at"] = source.ArrivalAt
	fields["clock"] = source.Clock
	if patch.Discarded == nil || !effectiveDiscard(row, *patch.Discarded) {
		fields["content_word_units"] = source.ContentUnits
	}
}

func stageServingSyncFields(fields, row, structured map[string]any, patch Finalization) {
	if patch.ServingSyncNotes {
		// Match the Python processing receipt when rich notes replace a minimum.
		if structured["title_provenance"] != nil {
			fields["structured.title_provenance"] = docstore.DeleteField
		}
		if row["summary_completed_at"] == nil && !field[bool](row, "summary_output_present") {
			fields["summary_title_provenance"] = "generated"
		}
	}
	if decision := patch.SyncRelevance; decision != nil {
		relevance := map[string]any{
			"verdict": decision.Verdict, "decided_by": decision.DecidedBy,
			"reason": decision.Reason, "rules_version": decision.RulesVersion, "trigger": "sync_update",
		}
		if decision.NeighborID != "" {
			relevance["neighbor_id"] = decision.NeighborID
		}
		if decision.Arm != "" {
			relevance["arm"] = decision.Arm
		}
		if decision.Jev != nil {
			relevance["jev"] = decision.Jev
		}
		fields["relevance_decision"] = relevance
	}
}

func stageSyncMinimumFields(fields, row map[string]any, minimum finalization.NotesMinimum) {
	discarded := effectiveDiscard(row, minimum.Discarded)
	verdict := "keep"
	if discarded {
		verdict = "discard"
	}
	if !discarded {
		fields["structured.title_provenance"] = "server_minimum"
		fields["summary_title_provenance"] = "server_minimum"
	}
	decidedBy := minimum.DecidedBy
	if decidedBy == "" {
		decidedBy = "rule"
	}
	fields["relevance_decision"] = map[string]any{
		"verdict": verdict, "decided_by": decidedBy, "reason": minimum.Reason,
		"rules_version": minimum.RulesVersion, "trigger": "sync_update",
	}
	fields[finalization.SyncMinimumRevisionField] = field[int64](row, "sync_content_revision")
	fields[finalization.SyncMinimumDiscardedField] = discarded
}

func effectiveTitle(row map[string]any, generated string) string {
	if title := field[string](row, "user_title"); strings.TrimSpace(title) != "" {
		return title
	}
	return generated
}

func effectiveOverview(row map[string]any, generated string) string {
	if overview := field[string](row, "user_overview"); overview != "" {
		return overview
	}
	return generated
}

func effectiveDiscard(row map[string]any, discarded bool) bool {
	return discarded && !field[bool](row, "sync_relevance_user_kept")
}

func validateStatus(patch Finalization) error {
	if patch.Status != nil {
		switch *patch.Status {
		case InProgress, Processing, Merging, Completed, Failed:
		default:
			return ErrStatus
		}
	}
	if patch.FinalizationStatus != nil {
		switch *patch.FinalizationStatus {
		case Queued, Leased, BlockedBYOK, Finalized, DeadLetter:
		default:
			return ErrStatus
		}
	}
	return nil
}

func refusesLifecycle(row map[string]any, patch Finalization) bool {
	status := Status(field[string](row, "status"))
	finalization := FinalizationStatus(field[string](row, "finalization_status"))
	statusChanged := patch.Status != nil && *patch.Status != status
	finalizationChanged := patch.FinalizationStatus != nil && *patch.FinalizationStatus != finalization
	discardChanged := patch.Discarded != nil && effectiveDiscard(row, *patch.Discarded) != field[bool](row, "discarded")

	if terminalFailure(row) {
		return statusChanged || finalizationChanged || discardChanged
	}
	return (status == Completed && statusChanged) || (finalization == Finalized && finalizationChanged)
}

func terminalFailure(row map[string]any) bool {
	switch field[string](row, "terminal_family") {
	case "dead_letter", "byok_abandoned", "oversized", "orphan_swept", "deferred_retry":
		return true
	default:
		return Status(field[string](row, "status")) == Failed || field[string](row, "finalization_status") == "dead_letter"
	}
}
