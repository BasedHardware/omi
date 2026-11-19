package conversations

import "strings"

func finalizationFields(row map[string]any, patch Finalization) (map[string]any, error) {
	if err := checkStatus(row, patch); err != nil {
		return nil, err
	}
	fields := make(map[string]any)
	if patch.Status != nil {
		fields["status"] = string(*patch.Status)
	}
	if patch.FinalizationStatus != nil {
		fields["finalization_status"] = string(*patch.FinalizationStatus)
	}
	if patch.Discarded != nil {
		fields["discarded"] = *patch.Discarded && !field[bool](row, "sync_relevance_user_kept")
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
	return fields, nil
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

func checkStatus(row map[string]any, patch Finalization) error {
	if patch.Status != nil {
		switch *patch.Status {
		case InProgress, Processing, Merging, Completed, Failed:
		default:
			return ErrStatus
		}
		if Status(field[string](row, "status")) == Completed && *patch.Status != Completed {
			return ErrStatus
		}
	}
	if patch.FinalizationStatus != nil {
		switch *patch.FinalizationStatus {
		case Queued, Leased, BlockedBYOK, Finalized, DeadLetter:
		default:
			return ErrStatus
		}
		if FinalizationStatus(field[string](row, "finalization_status")) == Finalized && *patch.FinalizationStatus != Finalized {
			return ErrStatus
		}
	}
	completing := patch.Status != nil && *patch.Status == Completed ||
		patch.FinalizationStatus != nil && *patch.FinalizationStatus == Finalized
	if completing && terminalFailure(row) {
		return ErrStatus
	}
	return nil
}

func terminalFailure(row map[string]any) bool {
	switch field[string](row, "terminal_family") {
	case "dead_letter", "byok_abandoned", "oversized", "orphan_swept", "deferred_retry":
		return true
	default:
		return Status(field[string](row, "status")) == Failed || field[string](row, "finalization_status") == "dead_letter"
	}
}
