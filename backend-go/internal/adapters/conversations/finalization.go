package conversations

import "strings"

func finalizationFields(row map[string]any, patch Finalization) (map[string]any, bool) {
	refused := refusesLifecycle(row, patch)
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
	stageNotesFields(fields, patch)
	return fields, refused
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
