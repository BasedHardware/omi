package finalizationdocs

import (
	"context"
	"math"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// BeginMergeRecovery transactionally chooses rollback, bounded cleanup
// redispatch, or a terminal manual recovery without allocating a new target.
func (s Store) BeginMergeRecovery(ctx context.Context, a queue.Admitting, owner, id string) (finalization.MergeRecoveryWork, error) {
	var result finalization.MergeRecoveryWork
	now := s.Clock.Now().UTC()
	err := s.withMerge(ctx, a, owner, id, func(tx *docstore.Tx, path docstore.Ref, row document) error {
		var recoveryErr error
		result, recoveryErr = beginMergeRecovery(tx, path, row, owner, id, now)
		return recoveryErr
	})
	return result, err
}

func beginMergeRecovery(tx *docstore.Tx, path docstore.Ref, row document, owner, id string, now time.Time) (finalization.MergeRecoveryWork, error) {
	due := field[time.Time](row, "reconcile_after_at")
	status := field[string](row, "status")
	if (status != queued && status != leased) || due.IsZero() || due.After(now) ||
		(status == leased && field[time.Time](row, "lease_expires_at").After(now)) {
		return finalization.MergeRecoveryWork{}, finalization.ErrStale
	}
	phase := rules.MergePhase(field[string](row, "phase"))
	action := rules.RecoverMerge(phase, field[int64](row, "attempt_count"))
	sources, err := mergeSources(row)
	if err != nil {
		return finalization.MergeRecoveryWork{}, err
	}
	job := finalization.MergeJob{ID: id, Owner: owner, Target: field[string](row, "merge_target_id"), Sources: sources,
		Generation: dispatchGeneration(row), Epoch: field[int64](row, "lease_epoch"), Phase: phase}
	if job.Epoch == math.MaxInt64 || job.Generation == math.MaxInt64 {
		return finalization.MergeRecoveryWork{}, finalization.ErrInvalid
	}
	switch action {
	case rules.MergeRecoveryNone:
		return finalization.MergeRecoveryWork{}, finalization.ErrStale
	case rules.MergeManual:
		row["status"], row["failure_code"], row["updated_at"] = deadLetter, "merge_cleanup_exhausted", now
		delete(row, "reconcile_after_at")
	case rules.MergeRollback:
		job.Epoch++
		job.Phase, job.LeaseUntil = rules.MergeRecovering, now.Add(mergeLease)
		row["status"], row["phase"], row["lease_epoch"] = leased, string(job.Phase), job.Epoch
		row["lease_expires_at"], row["reconcile_after_at"], row["updated_at"] = job.LeaseUntil, job.LeaseUntil, now
	case rules.MergeResumeCleanup:
		job.Epoch++
		job.Generation++
		row["status"], row["lease_epoch"], row["dispatch_generation"] = queued, job.Epoch, job.Generation
		row["reconcile_after_at"], row["updated_at"] = now.Add(mergeLease), now
	}
	return finalization.MergeRecoveryWork{Job: job, Action: action}, tx.Set(path, row)
}

// FinishMergeRollback releases only still-bound sources, after an authoritative
// transaction has observed that the exact provisional target is absent.
func (s Store) FinishMergeRollback(ctx context.Context, a queue.Admitting, claim finalization.MergeJob) error {
	now := s.Clock.Now().UTC()
	return s.withMerge(ctx, a, claim.Owner, claim.ID, func(tx *docstore.Tx, path docstore.Ref, row document) error {
		if field[string](row, "phase") != string(rules.MergeRecovering) ||
			field[int64](row, "lease_epoch") != claim.Epoch || dispatchGeneration(row) != claim.Generation ||
			field[string](row, "merge_target_id") != claim.Target || !field[time.Time](row, "lease_expires_at").After(now) {
			return queue.ErrLease
		}
		return finishMergeRollback(tx, path, row, claim, now)
	})
}

type rollbackSource struct {
	ref docstore.Ref
	row document
}

func finishMergeRollback(tx *docstore.Tx, path docstore.Ref, job document, claim finalization.MergeJob, now time.Time) error {
	target, err := conversationRef(finalization.Ref{Owner: claim.Owner, ID: claim.Target})
	if err != nil {
		return err
	}
	var row document
	found, err := tx.Get(target, &row)
	if err != nil {
		return err
	}
	if found {
		return finalization.ErrStale
	}
	updates, err := rollbackSources(tx, job, claim)
	if err != nil {
		return err
	}
	for _, source := range updates {
		source.row["status"] = string(rules.Completed)
		delete(source.row, "merge_job_id")
		if writeErr := tx.Set(source.ref, source.row); writeErr != nil {
			return writeErr
		}
	}
	job["phase"], job["status"], job["updated_at"] = string(rules.MergeRolledBack), completed, now
	delete(job, "reconcile_after_at")
	return tx.Set(path, job)
}

func rollbackSources(tx *docstore.Tx, job document, claim finalization.MergeJob) ([]rollbackSource, error) {
	ids, err := mergeSources(job)
	if err != nil {
		return nil, err
	}
	updates := make([]rollbackSource, 0, len(ids))
	for _, id := range ids {
		ref, pathErr := conversationRef(finalization.Ref{Owner: claim.Owner, ID: id})
		if pathErr != nil {
			return nil, pathErr
		}
		tombstone, pathErr := docstore.Doc("users", claim.Owner, "deleted_conversations", id)
		if pathErr != nil {
			return nil, pathErr
		}
		var row, marker document
		found, readErr := tx.Get(ref, &row)
		if readErr != nil {
			return nil, readErr
		}
		deleted, readErr := tx.Get(tombstone, &marker)
		if readErr != nil {
			return nil, readErr
		}
		if found && !deleted && !field[bool](row, "deleted") && field[string](row, "status") == string(rules.Merging) &&
			field[string](row, "merge_job_id") == claim.ID {
			updates = append(updates, rollbackSource{ref: ref, row: row})
		}
	}
	return updates, nil
}
