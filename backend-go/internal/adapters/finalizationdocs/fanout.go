package finalizationdocs

import (
	"context"
	"fmt"
	"maps"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// ClaimFanout checks the accepted epoch and current completed conversation in the
// same transaction as the fanout claim. A committed fanout is replayable.
func (s Store) ClaimFanout(ctx context.Context, g queue.Guarded, claim finalization.Claim) (finalization.Fanout, error) {
	var fanout finalization.Fanout
	err := s.withJob(ctx, g, claim, func(tx *docstore.Tx, ref docstore.Ref, job document, now time.Time, bound boundReader) error {
		var readErr error
		fanout, readErr = claimFanout(tx, ref, job, claim, now, bound)
		return readErr
	})
	if err != nil {
		return finalization.Fanout{}, err
	}
	return fanout, nil
}

func claimFanout(tx *docstore.Tx, ref docstore.Ref, job document, claim finalization.Claim, now time.Time, bound boundReader) (finalization.Fanout, error) {
	if field[string](job, "fanout_status") == completed {
		return finalization.Fanout{State: finalization.FanoutCommitted}, nil
	}
	if !owns(job, claim) {
		return finalization.Fanout{}, queue.ErrLease
	}
	binding := bound()
	if binding.err != nil {
		return finalization.Fanout{}, binding.err
	}
	row := binding.row
	if field[string](row, "status") != string(rules.Completed) {
		return finalization.Fanout{State: finalization.FanoutStale}, closeJob(tx, ref, job, finalization.TerminalStale, "", now)
	}
	return stageFanout(tx, ref, job, claim, now, fanoutSnapshot(row))
}

// ApplyAndClaimFanout stages finalization and its fanout intent under the
// same lease and source checks.
func (s Store) ApplyAndClaimFanout(ctx context.Context, g queue.Guarded, claim finalization.Claim, inline, minimum bool,
	apply func(*docstore.Tx, map[string]any) error,
) (finalization.Fanout, error) {
	if !s.SyncOnly {
		return finalization.Fanout{}, finalization.ErrInvalid
	}
	var fanout finalization.Fanout
	err := s.withJob(ctx, g, claim, func(tx *docstore.Tx, ref docstore.Ref, job document, now time.Time, bound boundReader) error {
		if !owns(job, claim) || field[string](job, "fanout_status") == completed {
			return queue.ErrLease
		}
		row := bound().row // withJob already checked the exact bound source.
		if err := apply(tx, row); err != nil {
			return err
		}
		snapshot := fanoutSnapshot(row)
		snapshot.NoDerivedEffects = snapshot.NoDerivedEffects || minimum
		if inline {
			fanout = finalization.Fanout{
				State: finalization.FanoutAcquired, Key: fanoutKey(job, claim), Conversation: snapshot,
			}
			return nil
		}
		var stageErr error
		fanout, stageErr = stageFanout(tx, ref, job, claim, now, snapshot)
		return stageErr
	})
	return fanout, err
}

func stageFanout(tx *docstore.Tx, ref docstore.Ref, job document, claim finalization.Claim, now time.Time, snapshot finalization.Conversation) (finalization.Fanout, error) {
	key := fanoutKey(job, claim)
	if err := tx.Update(ref, document{
		"fanout_status": leased, "fanout_key": key, "fanout_started_at": now,
		"fanout_lease_epoch": field[int64](job, "lease_epoch"), "go_fanout_sync_revision": snapshot.SyncRevision,
		"updated_at": now,
	}); err != nil {
		return finalization.Fanout{}, err
	}
	return finalization.Fanout{State: finalization.FanoutAcquired, Key: key, Conversation: snapshot}, nil
}

func fanoutKey(job document, claim finalization.Claim) string {
	key := field[string](job, "fanout_key")
	if key == "" {
		key = fmt.Sprintf("conversation:%s:finalization:%d", claim.Intent.Ref.ID, claim.Intent.Revision)
	}
	return key
}

func ownsSyncMinimum(row document) bool {
	revision := field[int64](row, "sync_content_revision")
	return revision > 0 && field[string](row, "finalization_engine") == "go" &&
		field[int64](row, finalization.SyncMinimumRevisionField) == revision
}

func fanoutSnapshot(row document) finalization.Conversation {
	structured := field[map[string]any](row, "structured")
	return finalization.Conversation{
		Status: rules.Completed, JobID: field[string](row, "finalization_job_id"),
		Revision: field[int64](row, "finalization_revision"), SyncRevision: field[int64](row, "sync_content_revision"),
		AppPlatform: field[string](row, "client_platform"), RecordingLayer: field[bool](row, "recording") || field[bool](row, "v3_derived"),
		NoDerivedEffects: field[bool](row, "terminal_no_derived_effects") || ownsSyncMinimum(row),
		UntrustedCapture: field[string](row, "capture_time_trust") == "untrusted",
		Notes:            finalization.Notes{Title: field[string](structured, "title"), Overview: field[string](structured, "overview")},
	}
}

// CompleteFanout commits only a claim owned by the current lease and only while
// the conversation remains bound, completed and undiscarded.
func (s Store) CompleteFanout(ctx context.Context, g queue.Guarded, claim finalization.Claim, dropped bool) (finalization.TerminalState, error) {
	state := finalization.TerminalPending
	err := s.withJob(ctx, g, claim, func(tx *docstore.Tx, ref docstore.Ref, job document, now time.Time, bound boundReader) error {
		state = finalization.TerminalPending
		if !owns(job, claim) {
			return queue.ErrLease
		}
		snapshot := bound()
		if snapshot.err != nil {
			return snapshot.err
		}
		row := snapshot.row
		if field[string](row, "status") != string(rules.Completed) {
			return finalization.ErrStale
		}
		if err := validateFanoutCompletion(job, row, claim, s.SyncOnly); err != nil {
			return err
		}
		if field[string](job, "fanout_status") == completed {
			return nil
		}
		patch := document{
			"fanout_status": completed, "fanout_completed_at": now, "updated_at": now,
			"go_delivery_dropped": dropped,
		}
		if !s.SyncOnly {
			return tx.Update(ref, patch)
		}
		// Sync has already settled its reference effects and episode receipts.
		// Commit fanout and job closure together under this same live binding.
		maps.Copy(job, patch)
		job["fanout_key"] = fanoutKey(job, claim)
		job["fanout_lease_epoch"] = field[int64](job, "lease_epoch")
		job["go_fanout_sync_revision"] = field[int64](row, "sync_content_revision")
		state = success(job)
		return closeJob(tx, ref, job, state, "", now)
	})
	return state, err
}

func validateFanoutCompletion(job, row document, claim finalization.Claim, syncOnly bool) error {
	// A fresh empty discard records the intent on the conversation in its
	// own write. Retried claims take the ordinary job-bound fanout path.
	if syncOnly && ownsSyncMinimum(row) && field[bool](row, finalization.SyncMinimumDiscardedField) &&
		field[int64](row, finalization.EmptyDiscardFanoutEpochField) == claim.Epoch {
		return nil
	}
	if syncOnly && field[int64](row, "go_sync_inline_fanout_epoch") == claim.Epoch {
		if field[int64](row, "go_sync_inline_fanout_revision") != field[int64](row, "sync_content_revision") {
			return changed()
		}
		return nil
	}
	if field[int64](job, "fanout_lease_epoch") != field[int64](job, "lease_epoch") {
		return queue.ErrLease
	}
	switch field[string](job, "fanout_status") {
	case completed:
		return nil
	case leased:
		if field[int64](job, "go_fanout_sync_revision") == field[int64](row, "sync_content_revision") {
			return nil
		}
		return changed()
	default:
		return finalization.ErrInvalid
	}
}

func owns(job document, claim finalization.Claim) bool {
	return field[string](job, "status") == leased && field[int64](job, queueEpochField) == claim.Epoch &&
		field[int64](job, wireEpochField) == field[int64](job, "lease_epoch")
}

func boundConversation(tx *docstore.Tx, claim finalization.Claim) (docstore.Ref, document, error) {
	ref, err := conversationRef(claim.Intent.Ref)
	if err != nil {
		return docstore.Ref{}, nil, err
	}
	deleted, err := conversationTombstoned(tx, claim.Intent.Ref)
	if err != nil || deleted {
		return ref, nil, err
	}
	var row document
	found, err := tx.Get(ref, &row)
	if err != nil {
		return ref, nil, err
	}
	// Only the exact Go short-clip discard may finish its existing claim.
	ownedDiscard := claim.Intent.Trigger == rules.SyncUpdate && ownsSyncMinimum(row) &&
		field[bool](row, finalization.SyncMinimumDiscardedField)
	if !found || field[bool](row, "deleted") || field[bool](row, "is_deleted") ||
		(field[bool](row, "discarded") && !ownedDiscard) || field[bool](row, "is_locked") || field[string](row, "data_protection_level") == "private" ||
		field[string](row, "finalization_job_id") != claim.Intent.JobID || field[int64](row, "finalization_revision") != claim.Intent.Revision {
		return ref, nil, nil
	}
	return ref, row, nil
}

func conversationTombstoned(tx *docstore.Tx, ref finalization.Ref) (bool, error) {
	tombstone, err := docstore.Doc("users", ref.Owner, "deleted_conversations", ref.ID)
	if err != nil {
		return false, err
	}
	var marker document
	return tx.Get(tombstone, &marker)
}
