package finalizationdocs

import (
	"context"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const minOversizeBytes = (1 << 20) - (64 << 10)

// ResolveQuietLimit handles only a named rejection from the current check's
// admission. Every refusal on the target leaves its successor armed.
func (s Store) ResolveQuietLimit(ctx context.Context, a queue.Admitting, wake finalization.QuietWake, cause error) (rules.QuietAction, bool, error) {
	limit, recognized := errors.AsType[*docstore.DocumentSizeError](cause)
	if !recognized {
		return rules.QuietWait, false, nil
	}
	now := s.Clock.Now().UTC()
	var action rules.QuietAction
	err := s.Docs.Fenced(ctx, a, wake.Check.Ref.Owner, func(tx *docstore.Tx) error {
		var limitErr error
		action, limitErr = resolveQuietLimit(tx, wake, limit.Names, limit.Named(), now)
		return limitErr
	})
	return action, true, classify(err)
}

func resolveQuietLimit(tx *docstore.Tx, wake finalization.QuietWake, names func(docstore.Ref) bool, named bool, now time.Time) (rules.QuietAction, error) {
	rows, err := getQuietRows(tx, wake.Check.Ref)
	if err != nil || !currentQuiet(rows.job, wake.Check.Generation) {
		return rules.QuietStale, err
	}
	if !named {
		return rules.QuietWait, nil
	}
	if !names(rows.conversationPath) {
		return rules.QuietRetire, retireQuiet(tx, rows.jobPath, rows.job, now, "document_size_limit")
	}
	current, written := rows.row, rows.written
	if written.IsZero() {
		return rules.QuietRetire, retireQuiet(tx, rows.jobPath, rows.job, now, "")
	}
	if !quietEligible(current) || field[bool](current, "deferred") || wake.Cutoff.IsZero() || wake.Cutoff.After(now) ||
		written.After(wake.Cutoff) || storedLowerBound(map[string]any(current)) < minOversizeBytes {
		return rules.QuietWait, nil
	}
	lease, err := recordingExpiry(tx, wake.Check.Ref, current)
	if err != nil || lease.After(now) {
		return rules.QuietWait, err
	}
	// This status-only update shrinks the document and preserves every retained field.
	if err := tx.Update(rows.conversationPath, document{"status": string(rules.Completed)}); err != nil {
		return rules.QuietWait, err
	}
	return rules.QuietRetire, retireQuiet(tx, rows.jobPath, rows.job, now, "document_size_limit")
}

// storedLowerBound follows Firestore's storage byte accounting for known values.
// Unknown SDK value types contribute zero rather than guessing a larger size.
func storedLowerBound(value any) int {
	switch v := value.(type) {
	case string:
		return len(v) + 1
	case []byte:
		return len(v)
	case int64, float64, time.Time:
		return 8
	case bool, nil:
		return 1
	case map[string]any:
		length := 0
		for key, child := range v {
			length += len(key) + 1 + storedLowerBound(child)
		}
		return length
	case []any:
		length := 0
		for _, child := range v {
			length += storedLowerBound(child)
		}
		return length
	default:
		return 0
	}
}
