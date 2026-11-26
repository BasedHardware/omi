package finalizationdocs

import (
	"context"
	"errors"
	"math"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	syncQuiet           = 30 * time.Second
	syncWaitLimit       = 600 * time.Second
	syncMaxRedispatches = 3
	goGeneration        = "go_dispatch_generation"
)

var errSyncWait = errors.New("finalization documents: sync revision quiet window")

// DeferSyncRevision rechecks the new revision and binding under the current lease.
// Firestore remembers the deadline across a crash before the SQL yield.
func (s Store) DeferSyncRevision(ctx context.Context, g queue.Guarded, claim finalization.Claim, expected int64) (time.Duration, error) {
	var delay time.Duration
	err := s.withJob(ctx, g, claim, func(tx *docstore.Tx, ref docstore.Ref, job document, now time.Time, bound boundReader) error {
		var deferErr error
		delay, deferErr = deferSync(tx, ref, job, claim, expected, now, bound)
		return deferErr
	})
	if err != nil {
		return 0, err
	}
	if delay == 0 {
		return 0, queue.Classify(errSyncWait, queue.Fence(finalization.CauseStale))
	}
	return delay, nil
}

func deferSync(tx *docstore.Tx, ref docstore.Ref, job document, claim finalization.Claim, expected int64, now time.Time, bound boundReader) (time.Duration, error) {
	if !owns(job, claim) {
		return 0, queue.ErrLease
	}
	if fanout := field[string](job, "fanout_status"); fanout != "" && fanout != "pending" {
		return 0, changed()
	}
	snapshot := bound()
	if snapshot.err != nil {
		return 0, snapshot.err
	}
	row := snapshot.row
	if row == nil {
		return 0, closeJob(tx, ref, job, finalization.TerminalStale, "", now)
	}
	observed := field[int64](row, "sync_content_revision")
	if field[string](row, "status") != string(rules.Processing) || observed <= expected {
		return 0, changed()
	}
	started := field[time.Time](job, "sync_revision_wait_started_at")
	if started.IsZero() {
		started = now
	}
	count := field[int64](job, "sync_revision_redispatch_count")
	if count >= syncMaxRedispatches || !now.Before(started.Add(syncWaitLimit)) || dispatchGeneration(job) == math.MaxInt64 {
		return 0, closeJob(tx, ref, job, finalization.TerminalStale, "", now)
	}
	delay := min(syncQuiet, started.Add(syncWaitLimit).Sub(now))
	return delay, queueSync(tx, ref, job, now, started, now.Add(delay), count, observed)
}

func changed() error {
	return queue.Classify(finalization.ErrSourceChanged, queue.Retry(finalization.CauseChanged, 0))
}

func queueSync(tx *docstore.Tx, ref docstore.Ref, job document, now, started, due time.Time, count, observed int64) error {
	generation := dispatchGeneration(job) + 1
	claims := field[int64](job, "worker_claim_count")
	if field[bool](job, "lease_counts_worker_attempt") {
		claims = max(0, claims-1)
	}
	if err := addProjection(tx, job, map[string]int64{leased: -1, queued: 1}); err != nil {
		return err
	}
	return tx.Update(ref, document{
		"status": queued, "updated_at": now, "lease_expires_at": now, "lease_counts_worker_attempt": false,
		"dispatch_generation": generation, goGeneration: generation, "worker_claim_count": claims,
		"sync_revision_waiting": true, "sync_revision_wait_started_at": started, "sync_revision_not_before": due,
		"sync_revision_redispatch_count": count + 1, "sync_revision_observed": observed,
		"reconcile_after_at": due, "last_failure_code": "sync_revision_advanced",
	})
}

func dispatchGeneration(job document) int64 {
	return max(1, field[int64](job, "dispatch_generation"))
}

func waitForSync(tx *docstore.Tx, ref docstore.Ref, job document, claim finalization.Claim, now time.Time) (bool, error) {
	if !field[bool](job, "sync_revision_waiting") {
		return false, nil
	}
	if claim.Epoch <= field[int64](job, queueEpochField) {
		return true, queue.ErrLease
	}
	started := field[time.Time](job, "sync_revision_wait_started_at")
	if started.IsZero() || !now.Before(started.Add(syncWaitLimit)) {
		return true, closeJob(tx, ref, job, finalization.TerminalStale, "", now)
	}
	if delay := field[time.Time](job, "sync_revision_not_before").Sub(now); delay > 0 {
		return true, queue.Classify(errSyncWait, queue.Yield(finalization.CauseChanged, delay))
	}
	return false, nil
}

// PrepareRedrive validates the parked queue epoch and reopens its bound job.
// The prior epoch is retained until a new queue claim starts.
func (s Store) PrepareRedrive(ctx context.Context, a queue.Admitting, intent finalization.Intent, previousEpoch int64, grants int) error {
	if intent.RequiresBYOK || previousEpoch <= 0 || grants < 0 {
		return finalization.ErrInvalid
	}
	ref, err := docstore.Doc(jobs, intent.JobID)
	if err != nil {
		return err
	}
	now := s.Clock.Now().UTC()
	return s.Docs.Fenced(ctx, a, intent.Ref.Owner, func(tx *docstore.Tx) error {
		return redrive(tx, ref, finalization.Claim{Intent: intent, Epoch: previousEpoch}, int64(grants), now)
	})
}

func redrive(tx *docstore.Tx, ref docstore.Ref, claim finalization.Claim, grants int64, now time.Time) error {
	var job document
	found, err := tx.Get(ref, &job)
	if err != nil {
		return err
	}
	intent, readErr := readIntent(claim.Intent.Ref, job, claim.Intent.JobID, claim.Intent.Revision)
	if !found || readErr != nil || intent != claim.Intent || claim.Epoch != field[int64](job, queueEpochField) {
		return queue.ErrState
	}
	_, row, err := boundConversation(tx, claim)
	if err != nil {
		return err
	}
	if field[string](row, "status") != string(rules.Completed) || field[string](job, "fanout_status") == completed {
		return queue.ErrState
	}
	if field[string](job, "status") == queued && field[int64](job, "go_redrive_epoch") == claim.Epoch {
		return nil
	}
	if terminal(job) != finalization.TerminalDeadLetter || dispatchGeneration(job) == math.MaxInt64 {
		return queue.ErrState
	}
	return reopen(tx, ref, job, claim.Epoch, grants, now)
}

func reopen(tx *docstore.Tx, ref docstore.Ref, job document, epoch, grants int64, now time.Time) error {
	if err := addProjection(tx, job, map[string]int64{deadLetter: -1, "failure": -1, queued: 1}); err != nil {
		return err
	}
	generation := dispatchGeneration(job) + 1
	job["status"], job["fanout_status"] = queued, "pending"
	job["dispatch_generation"], job[goGeneration], job["go_redrive_epoch"] = generation, generation, epoch
	job["budget_requeue_count"] = max(grants, field[int64](job, "budget_requeue_count"))
	job["updated_at"], job["reconcile_after_at"], job["dispatch_requested_at"] = now, now, now
	job["attempt_count"], job["worker_claim_count"], job["task_retry_count"] = int64(0), int64(0), int64(0)
	job["lease_counts_worker_attempt"], job["sync_revision_waiting"] = false, false
	for _, field := range []string{"terminal_at", "terminal_outcome", "last_failure_code", "lease_expires_at", "leased_at", "fanout_lease_epoch", "fanout_started_at", "sync_revision_wait_started_at", "sync_revision_not_before", "sync_revision_redispatch_count"} {
		delete(job, field)
	}
	return tx.Set(ref, job)
}
