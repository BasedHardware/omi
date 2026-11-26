package finalizationdocs

import (
	"context"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// ClaimRefresh binds the survivor revision to the current donor job epoch.
func (s Store) ClaimRefresh(ctx context.Context, g queue.Guarded, claim finalization.Claim, result finalization.SmartAbsorbResult) error {
	if err := s.updateRefresh(ctx, g, claim, result, false); err != nil {
		return err
	}
	return s.RepointEpisode(ctx, g, claim, result)
}

// CheckpointRefresh records that the currently owned revision was processed.
func (s Store) CheckpointRefresh(ctx context.Context, g queue.Guarded, claim finalization.Claim, result finalization.SmartAbsorbResult) error {
	return s.updateRefresh(ctx, g, claim, result, true)
}

func (s Store) updateRefresh(ctx context.Context, g queue.Guarded, claim finalization.Claim, result finalization.SmartAbsorbResult, checkpoint bool) error {
	if result.Survivor.Owner != claim.Intent.Ref.Owner || result.Revision <= 0 || result.Survivor.ID == claim.Intent.Ref.ID {
		return finalization.ErrInvalid
	}
	return s.withJob(ctx, g, claim, func(tx *docstore.Tx, _ docstore.Ref, job document, now time.Time) error {
		if !owns(job, claim) || !field[time.Time](job, "lease_expires_at").After(now) {
			return queue.ErrLease
		}
		for _, ref := range []finalization.Ref{claim.Intent.Ref, result.Survivor} {
			deleted, err := conversationTombstoned(tx, ref)
			if err != nil {
				return err
			}
			if deleted {
				return finalization.ErrStale
			}
		}
		donor, err := conversationRef(claim.Intent.Ref)
		if err != nil {
			return err
		}
		var donorRow document
		if _, readErr := tx.Get(donor, &donorRow); readErr != nil {
			return readErr
		}
		if !field[bool](donorRow, "deleted") || field[string](donorRow, "sync_merged_into") != result.Survivor.ID ||
			field[string](donorRow, "finalization_job_id") != claim.Intent.JobID ||
			field[int64](donorRow, "finalization_revision") != claim.Intent.Revision {
			return finalization.ErrStale
		}
		return writeRefresh(tx, claim, result, now, checkpoint)
	})
}

func writeRefresh(tx *docstore.Tx, claim finalization.Claim, result finalization.SmartAbsorbResult, now time.Time, checkpoint bool) error {
	path, err := conversationRef(result.Survivor)
	if err != nil {
		return err
	}
	var row document
	if _, readErr := tx.Get(path, &row); readErr != nil {
		return readErr
	}
	state := field[map[string]any](row, "smart_merge")
	if !absorbVisible(row) || field[int64](state, "revision") != result.Revision ||
		field[int64](row, "sync_content_revision") != result.SyncRevision {
		return finalization.ErrStale
	}
	lease := field[map[string]any](state, "refresh_lease")
	current := field[time.Time](lease, "until").After(now)
	matches := field[string](lease, "owner") == claim.Intent.JobID && field[int64](lease, "go_epoch") == claim.Epoch
	if checkpoint {
		if !current || !matches {
			return queue.ErrLease
		}
		state["processed_revision"], state["processed_sync_revision"] = result.Revision, result.SyncRevision
	} else {
		if current && !matches && field[string](lease, "owner") != claim.Intent.JobID {
			return queue.ErrLease
		}
		state["refresh_lease"] = document{"owner": claim.Intent.JobID, "go_epoch": claim.Epoch, "until": now.Add(time.Minute)}
	}
	return tx.Update(path, document{"smart_merge": state})
}
