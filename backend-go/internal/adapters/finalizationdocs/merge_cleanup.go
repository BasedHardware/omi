package finalizationdocs

import (
	"context"
	"slices"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// MergeRetraction is the idempotent cleanup of source-owned derived data.
// It may return success only after authoritative retraction has committed;
// paid processing and source document deletion belong to separate operations.
type MergeRetraction interface {
	Retract(ctx context.Context, a queue.Admitting, claim finalization.MergeJob, source string) error
}

// CleanupMergeSource validates a sealed source before and after retraction,
// never deleting it after the survivor disappears or the lease changes.
func (s Store) CleanupMergeSource(ctx context.Context, a queue.Admitting, claim finalization.MergeJob, id string) error {
	found, err := s.checkedMergeSource(ctx, a, claim, id, false)
	if err != nil || !found {
		return err
	}
	if s.MergeRetraction == nil {
		return ErrUnsupported
	}
	if retractErr := s.MergeRetraction.Retract(ctx, a, claim, id); retractErr != nil {
		return retractErr
	}
	_, err = s.checkedMergeSource(ctx, a, claim, id, true)
	return err
}

func (s Store) checkedMergeSource(ctx context.Context, a queue.Admitting, claim finalization.MergeJob, id string, remove bool) (bool, error) {
	now := s.Clock.Now().UTC()
	var found bool
	err := s.withMerge(ctx, a, claim.Owner, claim.ID, func(tx *docstore.Tx, _ docstore.Ref, row document) error {
		sources, err := checkSealedMerge(tx, claim, row, now)
		if err != nil {
			return err
		}
		if !slices.Equal(sources, claim.Sources) || !slices.Contains(sources, id) {
			return finalization.ErrInvalid
		}
		var source docstore.Ref
		var sourceErr error
		source, found, sourceErr = readMergeCleanupSource(tx, claim, id)
		if sourceErr != nil || !found || !remove {
			return sourceErr
		}
		marker, err := docstore.Doc("users", claim.Owner, "deleted_conversations", id)
		if err != nil {
			return err
		}
		if err := tx.Set(marker, document{"conversation_id": id, "deleted_at": now, "sync_merged_into": claim.Target}); err != nil {
			return err
		}
		return tx.Delete(source)
	})
	return found, err
}

func checkSealedMerge(tx *docstore.Tx, claim finalization.MergeJob, row document, now time.Time) ([]string, error) {
	if field[string](row, "status") != leased || field[string](row, "phase") != string(rules.MergeSourceCleanup) ||
		field[string](row, "merge_target_id") != claim.Target || dispatchGeneration(row) != claim.Generation ||
		field[int64](row, "lease_epoch") != claim.Epoch || field[int64](row, "go_cleanup_epoch") != claim.Epoch ||
		!field[time.Time](row, "lease_expires_at").After(now) {
		return nil, queue.ErrLease
	}
	ref := finalization.Ref{Owner: claim.Owner, ID: claim.Target}
	path, err := conversationRef(ref)
	if err != nil {
		return nil, err
	}
	tombstone, err := docstore.Doc("users", ref.Owner, "deleted_conversations", ref.ID)
	if err != nil {
		return nil, err
	}
	var survivor, marker document
	found, err := tx.Get(path, &survivor)
	if err != nil {
		return nil, err
	}
	deleted, err := tx.Get(tombstone, &marker)
	if err != nil {
		return nil, err
	}
	if !found || deleted || !absorbVisible(survivor) || field[string](survivor, "status") != string(rules.Completed) {
		return nil, finalization.ErrStale
	}
	return mergeSources(row)
}

func readMergeCleanupSource(tx *docstore.Tx, claim finalization.MergeJob, id string) (docstore.Ref, bool, error) {
	path, err := conversationRef(finalization.Ref{Owner: claim.Owner, ID: id})
	if err != nil {
		return path, false, err
	}
	var row document
	found, err := tx.Get(path, &row)
	if err != nil || !found {
		return path, false, err
	}
	if field[bool](row, "deleted") && field[string](row, "sync_merged_into") == claim.Target {
		return path, false, nil
	}
	if field[bool](row, "deleted") || field[bool](row, "is_locked") ||
		field[string](row, "merge_job_id") != claim.ID || field[string](row, "transcript_corrections_moved_to") != claim.Target {
		return path, false, finalization.ErrStale
	}
	tombstone, err := docstore.Doc("users", claim.Owner, "deleted_conversations", id)
	if err != nil {
		return path, false, err
	}
	var marker document
	deleted, err := tx.Get(tombstone, &marker)
	if err != nil {
		return path, false, err
	}
	if deleted {
		return path, false, finalization.ErrStale
	}

	return path, true, nil
}

// CompleteMergeCleanup closes a sealed job only when no owned sources remain.
func (s Store) CompleteMergeCleanup(ctx context.Context, a queue.Admitting, claim finalization.MergeJob) error {
	now := s.Clock.Now().UTC()
	return s.withMerge(ctx, a, claim.Owner, claim.ID, func(tx *docstore.Tx, path docstore.Ref, row document) error {
		if field[string](row, "status") == completed && field[int64](row, "lease_epoch") == claim.Epoch &&
			field[string](row, "merge_target_id") == claim.Target && dispatchGeneration(row) == claim.Generation {
			return nil
		}
		sources, err := checkSealedMerge(tx, claim, row, now)
		if err != nil {
			return err
		}
		for _, id := range sources {
			_, found, checkErr := readMergeCleanupSource(tx, claim, id)
			if checkErr != nil {
				return checkErr
			}
			if found {
				return finalization.ErrStale
			}
		}
		row["status"], row["updated_at"], row["completed_at"] = completed, now, now
		delete(row, "reconcile_after_at")
		return tx.Set(path, row)
	})
}
