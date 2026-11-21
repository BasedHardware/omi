package finalizationdocs

import (
	"context"
	"crypto/rand"
	"fmt"
	"math"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	mergeKind  = "conversation_merge"
	mergeLease = 10 * time.Minute
)

func newUUID() (string, error) {
	var id [16]byte
	if _, err := rand.Read(id[:]); err != nil {
		return "", err
	}
	id[6] = id[6]&0x0f | 0x40
	id[8] = id[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", id[:4], id[4:6], id[6:8], id[8:10], id[10:]), nil
}

// AdmitMerge binds the whole eligible source set or writes nothing.
func (s Store) AdmitMerge(ctx context.Context, a queue.Admitting, req finalization.MergeRequest) (finalization.MergeJob, error) {
	if !distinctSources(req.Sources) {
		return finalization.MergeJob{}, finalization.ErrInvalid
	}
	id, err := newUUID()
	if err != nil {
		return finalization.MergeJob{}, err
	}
	target, err := newUUID()
	if err != nil {
		return finalization.MergeJob{}, err
	}
	job := finalization.MergeJob{ID: "merge-" + id, Owner: req.Owner, Target: target, Sources: req.Sources, Generation: 1, Phase: rules.MergePreparing}
	now := s.Clock.Now().UTC()
	err = s.Docs.Fenced(ctx, a, req.Owner, func(tx *docstore.Tx) error {
		return admitMerge(tx, job, req.Reprocess, now)
	})
	if err != nil {
		return finalization.MergeJob{}, classify(err)
	}
	return job, nil
}

func distinctSources(sources []string) bool {
	if len(sources) < 2 || len(sources) > 100 {
		return false
	}
	seen := make(map[string]bool, len(sources))
	for _, id := range sources {
		if id == "" || seen[id] {
			return false
		}
		seen[id] = true
	}
	return true
}

func admitMerge(tx *docstore.Tx, job finalization.MergeJob, reprocess bool, now time.Time) error {
	sourceRefs := make([]docstore.Ref, 0, len(job.Sources))
	for _, id := range job.Sources {
		ref, err := mergeSource(tx, job.Owner, id, "")
		if err != nil {
			return err
		}
		sourceRefs = append(sourceRefs, ref)
	}
	path, err := docstore.Doc(jobs, job.ID)
	if err != nil {
		return err
	}
	if err := tx.Create(path, document{
		"kind": mergeKind, "uid": job.Owner, "conversation_ids": job.Sources, "merge_target_id": job.Target,
		"status": queued, "phase": string(job.Phase), "dispatch_generation": int64(1), "lease_epoch": int64(0),
		"attempt_count": int64(0), "reprocess": reprocess, "created_at": now, "updated_at": now, "reconcile_after_at": now.Add(mergeLease),
	}); err != nil {
		return err
	}
	for _, ref := range sourceRefs {
		if err := tx.Update(ref, document{"status": string(rules.Merging), "merge_job_id": job.ID}); err != nil {
			return err
		}
	}
	return nil
}

func mergeSource(tx *docstore.Tx, owner, id, jobID string) (docstore.Ref, error) {
	ref, err := conversationRef(finalization.Ref{Owner: owner, ID: id})
	if err != nil {
		return ref, err
	}
	tombstone, err := docstore.Doc("users", owner, "deleted_conversations", id)
	if err != nil {
		return ref, err
	}
	var row, marker document
	found, err := tx.Get(ref, &row)
	if err != nil {
		return ref, err
	}
	deleted, err := tx.Get(tombstone, &marker)
	if err != nil {
		return ref, err
	}
	if !found || deleted || field[bool](row, "deleted") || field[bool](row, "is_locked") || field[string](row, "merge_job_id") != jobID {
		return ref, finalization.ErrStale
	}
	status := field[string](row, "status")
	if (jobID == "" && (status != string(rules.Completed) || receivedMerge(row))) ||
		(jobID != "" && status != string(rules.Merging)) {
		return ref, finalization.ErrStale
	}
	return ref, nil
}

func receivedMerge(row document) bool {
	return field[string](row, "transcript_corrections_moved_to") != ""
}

// ClaimMerge acquires only the current queued merge generation.
func (s Store) ClaimMerge(ctx context.Context, a queue.Admitting, owner, id string, generation int64) (finalization.MergeJob, error) {
	var claim finalization.MergeJob
	now := s.Clock.Now().UTC()
	err := s.withMerge(ctx, a, owner, id, func(tx *docstore.Tx, path docstore.Ref, row document) error {
		if generation <= 0 || generation != field[int64](row, "dispatch_generation") || field[string](row, "status") != queued {
			return finalization.ErrStale
		}
		offset := field[int64](row, "lease_epoch")
		if offset < 0 || offset == math.MaxInt64 {
			return finalization.ErrInvalid
		}
		sources, sourceErr := mergeSources(row)
		if sourceErr != nil {
			return sourceErr
		}
		attempts := field[int64](row, "attempt_count") + 1
		claim = finalization.MergeJob{
			ID: id, Owner: owner, Target: field[string](row, "merge_target_id"), Sources: sources,
			Generation: generation, Epoch: offset + 1, Phase: rules.MergePhase(field[string](row, "phase")), LeaseUntil: now.Add(mergeLease),
		}
		patch := document{"status": leased, "lease_epoch": claim.Epoch, "attempt_count": attempts,
			"lease_expires_at": claim.LeaseUntil, "reconcile_after_at": claim.LeaseUntil, "updated_at": now}
		if claim.Phase == rules.MergeSourceCleanup {
			patch["go_cleanup_epoch"] = claim.Epoch
		}
		return tx.Update(path, patch)
	})
	return claim, err
}

// RenewMerge extends the current lease and checks every source before sealing.
func (s Store) RenewMerge(ctx context.Context, a queue.Admitting, claim finalization.MergeJob, seal bool) error {
	now := s.Clock.Now().UTC()
	return s.withMerge(ctx, a, claim.Owner, claim.ID, func(tx *docstore.Tx, path docstore.Ref, row document) error {
		if field[string](row, "status") != leased || claim.Epoch != field[int64](row, "lease_epoch") ||
			claim.Generation != field[int64](row, "dispatch_generation") || !field[time.Time](row, "lease_expires_at").After(now) {
			return queue.ErrLease
		}
		until := now.Add(mergeLease)
		update := document{"lease_expires_at": until, "reconcile_after_at": until, "updated_at": now}
		if seal {
			if err := checkMergeSeal(tx, claim, row); err != nil {
				return err
			}
			update["phase"] = string(rules.MergeSourceCleanup)
			update["go_cleanup_epoch"] = claim.Epoch
		}
		return tx.Update(path, update)
	})
}

func checkMergeSeal(tx *docstore.Tx, claim finalization.MergeJob, row document) error {
	if field[string](row, "phase") != string(rules.MergePreparing) || field[string](row, "merge_target_id") != claim.Target {
		return finalization.ErrStale
	}
	sources, err := mergeSources(row)
	if err != nil {
		return err
	}
	for _, id := range sources {
		if _, sourceErr := mergeSource(tx, claim.Owner, id, claim.ID); sourceErr != nil {
			return sourceErr
		}
	}
	return nil
}

func mergeSources(row document) ([]string, error) {
	raw := field[[]any](row, "conversation_ids")
	var ids []string
	for _, value := range raw {
		id, ok := value.(string)
		if !ok {
			return nil, finalization.ErrInvalid
		}
		ids = append(ids, id)
	}
	if !distinctSources(ids) {
		return nil, finalization.ErrInvalid
	}
	return ids, nil
}

func (s Store) withMerge(ctx context.Context, a queue.Admitting, owner, id string, fn func(*docstore.Tx, docstore.Ref, document) error) error {
	path, err := docstore.Doc(jobs, id)
	if err != nil {
		return err
	}
	err = s.Docs.Fenced(ctx, a, owner, func(tx *docstore.Tx) error {
		var row document
		found, readErr := tx.Get(path, &row)
		if readErr != nil {
			return readErr
		}
		if !found || field[string](row, "kind") != mergeKind || field[string](row, "uid") != owner {
			return finalization.ErrStale
		}
		return fn(tx, path, row)
	})
	return classify(err)
}
