package finalizationdocs

import (
	"bytes"
	"context"
	"encoding/json"
	"math"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const firstSummaryDeadline = 120 * time.Second

func stageSummaryRearm(previous, patch document, now time.Time) {
	before := field[int64](previous, "sync_content_revision")
	after := field[int64](patch, "sync_content_revision")
	rearms := field[int64](previous, "summary_empty_rearms")
	exhausted := field[string](previous, "summary_blocked_reason") == "empty_output_exhausted"
	switch rules.RearmSummary(before, after, rearms, exhausted, summaryDebt(previous).HasSummary) {
	case rules.SummaryKeepBlocked:
	case rules.SummaryResetEmpty:
		patch["summary_blocked_reason"], patch["summary_empty_failures"] = nil, int64(0)
		patch["summary_empty_rearms"], patch["summary_due_at"] = rearms+1, unix(now.Add(firstSummaryDeadline))
	case rules.SummaryLifetimeBlocked:
		patch["summary_blocked_reason"], patch["summary_due_at"] = "empty_output_lifetime_exhausted", nil
	}
}

// CommitInlineSyncRevision commits a standard inline transcript revision and
// any summary-debt rearm together. Object-lake and enhanced writes need the
// existing sync codec to include stageSummaryRearm in their content transaction.
func (s Store) CommitInlineSyncRevision(ctx context.Context, a queue.Admitting, ref finalization.Ref, expected int64, written time.Time, segments []json.RawMessage) error {
	if expected < 0 || expected == math.MaxInt64 || written.IsZero() {
		return finalization.ErrInvalid
	}
	path, err := conversationRef(ref)
	if err != nil {
		return err
	}
	decoded, err := inlineSegments(segments)
	if err != nil {
		return err
	}
	now := s.Clock.Now().UTC()
	return classify(s.Docs.Fenced(ctx, a, ref.Owner, func(tx *docstore.Tx) error {
		var row document
		version, err := tx.GetVersion(path, &row)
		if err != nil {
			return err
		}
		if !version.Equal(written) || !inlineSyncRevisionRow(row, expected) {
			return finalization.ErrStale
		}
		old, err := json.Marshal(row["transcript_segments"])
		if err != nil {
			return finalization.ErrInvalid
		}
		updated, err := json.Marshal(decoded)
		if err != nil {
			return finalization.ErrInvalid
		}
		if bytes.Equal(old, updated) {
			return nil
		}
		patch := document{"sync_content_revision": expected + 1, "transcript_segments": decoded, "has_content": true}
		stageSummaryRearm(row, patch, now)
		if storedLowerBound(map[string]any(row))+len(updated) > 900<<10 {
			return finalization.ErrInvalid
		}
		return tx.Update(path, patch)
	}))
}

func inlineSyncRevisionRow(row document, expected int64) bool {
	_, inline := row["transcript_segments"].([]any)
	return absorbVisible(row) && !field[bool](row, "is_deleted") &&
		(inline || row["transcript_segments"] == nil) && field[int64](row, "sync_content_revision") == expected &&
		field[string](row, "data_protection_level") == "standard" && !field[bool](row, "transcript_segments_compressed") &&
		field[string](row, "sync_merged_into") == "" && !field[bool](row, "has_transcript_corrections")
}

func inlineSegments(segments []json.RawMessage) ([]map[string]any, error) {
	if len(segments) == 0 {
		return nil, finalization.ErrInvalid
	}
	result := make([]map[string]any, 0, len(segments))
	for _, raw := range segments {
		var entry map[string]any
		if json.Unmarshal(raw, &entry) != nil || entry == nil {
			return nil, finalization.ErrInvalid
		}
		result = append(result, entry)
	}
	return result, nil
}
