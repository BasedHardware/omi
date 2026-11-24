package finalizationdocs

import (
	"context"
	"errors"
	"math"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	queueEpochField = "go_queue_epoch"
	wireEpochField  = "go_lease_epoch"
)

var (
	errForeignLease      = errors.New("finalization documents: previous dispatcher owns lease")
	errForeignGeneration = errors.New("finalization documents: dispatch generation changed")
)

// Begin mirrors a SQL claim in Firestore. A job attached from the Python outbox
// must be in generation one or a successor recorded by Go, with no live foreign lease. Deployments
// must cut over dispatch ownership before using this adapter.
func (s Store) Begin(ctx context.Context, g queue.Guarded, claim finalization.Claim) error {
	return s.withJob(ctx, g, claim, func(tx *docstore.Tx, ref docstore.Ref, job document, now time.Time) error {
		if terminal(job) != finalization.TerminalPending {
			return nil
		}
		if stop, err := waitForSync(tx, ref, job, claim, now); stop || err != nil {
			return err
		}
		return begin(tx, ref, job, claim, now)
	})
}

func begin(tx *docstore.Tx, ref docstore.Ref, job document, claim finalization.Claim, now time.Time) error {
	previous := field[int64](job, queueEpochField)
	epoch := field[int64](job, "lease_epoch")
	status := field[string](job, "status")
	if previous == claim.Epoch && owns(job, claim) {
		return nil
	}
	if previous >= claim.Epoch || epoch == math.MaxInt64 {
		return queue.ErrLease
	}
	if status == leased && (previous == 0 || epoch != field[int64](job, wireEpochField)) && field[time.Time](job, "lease_expires_at").After(now) {
		return queue.Classify(errForeignLease, queue.Yield(CauseForeignLease, 30*time.Second))
	}
	if claim.Intent.RequiresBYOK && !claim.LiveBYOK {
		return queue.Classify(ErrUnsupported, queue.BlockForSecret())
	}
	if status != queued && status != blocked && status != leased {
		return finalization.ErrInvalid
	}
	if status != leased {
		if err := addProjection(tx, job, map[string]int64{status: -1, leased: 1}); err != nil {
			return err
		}
	}
	lease, _, _, _ := finalization.Defaults()
	claims := field[int64](job, "worker_claim_count")
	attempts, taskRetries := field[int64](job, "attempt_count"), field[int64](job, "task_retry_count")
	grants := field[int64](job, "budget_requeue_count")
	if current := int64(claim.BudgetRequeues); current > grants {
		grants, claims, attempts, taskRetries = current, 0, 0, 0
	}
	if !claim.Reconcile {
		claims++
	}
	return tx.Update(ref, document{
		"status": leased, queueEpochField: claim.Epoch, "lease_epoch": epoch + 1, wireEpochField: epoch + 1,
		"worker_claim_count": claims, "attempt_count": attempts, "task_retry_count": taskRetries,
		"budget_requeue_count": grants, "sync_revision_waiting": false,
		"lease_counts_worker_attempt": !claim.Reconcile, "leased_at": now, "lease_expires_at": now.Add(lease),
		"updated_at": now, "reconcile_after_at": now.Add(lease),
	})
}

func (s Store) withJob(ctx context.Context, g queue.Guarded, claim finalization.Claim,
	fn func(*docstore.Tx, docstore.Ref, document, time.Time) error,
) error {
	ref, err := docstore.Doc(jobs, claim.Intent.JobID)
	if err != nil || claim.Epoch <= 0 {
		return classify(finalization.ErrInvalid)
	}
	now := s.Clock.Now().UTC()
	err = s.Docs.Fenced(ctx, g, claim.Intent.Ref.Owner, func(tx *docstore.Tx) error {
		var job document
		found, readErr := tx.Get(ref, &job)
		if readErr != nil {
			return readErr
		}
		if !found {
			return finalization.ErrStale
		}
		intent, readErr := readIntent(claim.Intent.Ref, job, claim.Intent.JobID, claim.Intent.Revision)
		if readErr != nil || intent != claim.Intent {
			return queue.ErrLease
		}
		if gen := dispatchGeneration(job); gen > 1 && field[int64](job, goGeneration) != gen {
			return queue.Classify(errForeignGeneration, queue.Fence(CauseForeignLease))
		}
		return fn(tx, ref, job, now)
	})
	if _, ok := errors.AsType[queue.Classified](err); ok {
		return err
	}
	return classify(err)
}
