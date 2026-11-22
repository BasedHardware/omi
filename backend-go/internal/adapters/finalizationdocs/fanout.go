package finalizationdocs

import (
	"context"
	"fmt"
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
	err := s.withJob(ctx, g, claim, func(tx *docstore.Tx, ref docstore.Ref, job document, now time.Time) error {
		var readErr error
		fanout, readErr = claimFanout(tx, ref, job, claim, now)
		return readErr
	})
	if err != nil {
		return finalization.Fanout{}, err
	}
	return fanout, nil
}

func claimFanout(tx *docstore.Tx, ref docstore.Ref, job document, claim finalization.Claim, now time.Time) (finalization.Fanout, error) {
	if field[string](job, "fanout_status") == completed {
		return finalization.Fanout{State: finalization.FanoutCommitted}, nil
	}
	if !owns(job, claim) {
		return finalization.Fanout{}, queue.ErrLease
	}
	_, row, err := boundConversation(tx, claim)
	if err != nil {
		return finalization.Fanout{}, err
	}
	if field[string](row, "status") != string(rules.Completed) {
		return finalization.Fanout{State: finalization.FanoutStale}, closeJob(tx, ref, job, finalization.TerminalStale, "", now)
	}
	key := field[string](job, "fanout_key")
	if key == "" {
		key = fmt.Sprintf("conversation:%s:finalization:%d", claim.Intent.Ref.ID, claim.Intent.Revision)
	}
	snapshot := fanoutSnapshot(row)
	if err := tx.Update(ref, document{
		"fanout_status": leased, "fanout_key": key, "fanout_started_at": now,
		"fanout_lease_epoch": field[int64](job, "lease_epoch"), "go_fanout_sync_revision": snapshot.SyncRevision,
		"updated_at": now,
	}); err != nil {
		return finalization.Fanout{}, err
	}
	return finalization.Fanout{State: finalization.FanoutAcquired, Key: key, Conversation: snapshot}, nil
}

func fanoutSnapshot(row document) finalization.Conversation {
	structured := field[map[string]any](row, "structured")
	return finalization.Conversation{
		Status: rules.Completed, JobID: field[string](row, "finalization_job_id"),
		Revision: field[int64](row, "finalization_revision"), SyncRevision: field[int64](row, "sync_content_revision"),
		AppPlatform: field[string](row, "client_platform"), RecordingLayer: field[bool](row, "recording") || field[bool](row, "v3_derived"),
		NoDerivedEffects: field[bool](row, "terminal_no_derived_effects"),
		UntrustedCapture: field[string](row, "capture_time_trust") == "untrusted",
		Notes:            finalization.Notes{Title: field[string](structured, "title"), Overview: field[string](structured, "overview")},
	}
}

// CompleteFanout commits only a claim owned by the current lease and only while
// the conversation remains bound, completed and undiscarded.
func (s Store) CompleteFanout(ctx context.Context, g queue.Guarded, claim finalization.Claim, dropped bool) error {
	return s.withJob(ctx, g, claim, func(tx *docstore.Tx, ref docstore.Ref, job document, now time.Time) error {
		if !owns(job, claim) || field[int64](job, "fanout_lease_epoch") != field[int64](job, "lease_epoch") {
			return queue.ErrLease
		}
		switch field[string](job, "fanout_status") {
		case completed:
			return nil
		case leased:
		default:
			return finalization.ErrInvalid
		}
		_, row, err := boundConversation(tx, claim)
		if err != nil {
			return err
		}
		if field[string](row, "status") != string(rules.Completed) {
			return finalization.ErrStale
		}
		if field[int64](job, "go_fanout_sync_revision") != field[int64](row, "sync_content_revision") {
			return queue.Classify(finalization.ErrInvalid, queue.Retry(finalization.CauseChanged, 0))
		}
		return tx.Update(ref, document{
			"fanout_status": completed, "fanout_completed_at": now, "updated_at": now,
			"go_delivery_dropped": dropped,
		})
	})
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
	if !found || field[bool](row, "deleted") || field[bool](row, "is_deleted") ||
		field[bool](row, "discarded") || field[bool](row, "is_locked") || field[string](row, "data_protection_level") == "private" ||
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
