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

// ReconcileCompletion closes a previously committed fanout under the current lease.
func (s Store) ReconcileCompletion(ctx context.Context, g queue.Guarded, claim finalization.Claim) (finalization.TerminalState, error) {
	return s.finish(ctx, g, claim, terminalRequest{state: finalization.TerminalPending})
}

// Fence closes only the stale job. A previous fanout commit retains precedence.
func (s Store) Fence(ctx context.Context, g queue.Guarded, claim finalization.Claim) (finalization.TerminalState, error) {
	return s.finish(ctx, g, claim, terminalRequest{state: finalization.TerminalStale})
}

// DeadLetter closes an exhausted job and its still-bound processing row together.
func (s Store) DeadLetter(ctx context.Context, g queue.Guarded, claim finalization.Claim, cause queue.Cause, transient bool) (finalization.TerminalState, error) {
	return s.finish(ctx, g, claim, terminalRequest{state: finalization.TerminalDeadLetter, cause: cause, transient: transient})
}

type terminalRequest struct {
	state     finalization.TerminalState
	cause     queue.Cause
	transient bool
}

func (s Store) finish(ctx context.Context, g queue.Guarded, claim finalization.Claim, request terminalRequest) (finalization.TerminalState, error) {
	var state finalization.TerminalState
	err := s.withJob(ctx, g, claim, func(tx *docstore.Tx, ref docstore.Ref, job document, now time.Time) error {
		var finishErr error
		state, finishErr = finish(tx, ref, job, claim, request, now)
		return finishErr
	})
	if errors.Is(err, finalization.ErrStale) {
		return finalization.TerminalStale, nil
	}
	if err != nil {
		return finalization.TerminalPending, err
	}
	return state, nil
}

func finish(tx *docstore.Tx, ref docstore.Ref, job document, claim finalization.Claim, req terminalRequest, now time.Time) (finalization.TerminalState, error) {
	if state := terminal(job); state != finalization.TerminalPending {
		return state, nil
	}
	if !owns(job, claim) {
		return finalization.TerminalPending, queue.ErrLease
	}
	state := req.state
	var update func() error
	switch {
	case field[string](job, "fanout_status") == completed:
		state = success(job)
	case state == finalization.TerminalPending:
		return state, nil
	case state == finalization.TerminalStale || state == finalization.TerminalDeadLetter:
		var finishErr error
		state, update, finishErr = prepareTerminalConversation(tx, claim, req, now)
		if finishErr != nil || state == finalization.TerminalPending {
			return state, finishErr
		}
	}
	if err := closeJob(tx, ref, job, state, req.cause, now); err != nil || update == nil {
		return state, err
	}
	return state, update()
}

func prepareTerminalConversation(tx *docstore.Tx, claim finalization.Claim, req terminalRequest, now time.Time) (finalization.TerminalState, func() error, error) {
	ref, row, err := boundConversation(tx, claim)
	if err != nil || row == nil {
		return finalization.TerminalStale, nil, err
	}
	status := rules.Status(field[string](row, "status"))
	if req.state == finalization.TerminalStale {
		if status == rules.Processing || status == rules.Completed {
			return finalization.TerminalPending, nil, nil
		}
		return finalization.TerminalStale, nil, nil
	}
	if status != rules.Processing {
		return req.state, nil, nil
	}
	update, err := prepareFailure(tx, claim, ref, row, req, now)
	return req.state, update, err
}

func closeJob(tx *docstore.Tx, ref docstore.Ref, job document, state finalization.TerminalState, cause queue.Cause, now time.Time) error {
	delta := map[string]int64{field[string](job, "status"): -1}
	status, outcome := completed, "success"
	job["last_failure_code"] = nil
	switch state {
	case finalization.TerminalComplete, finalization.TerminalDeliveryDropped:
		job["completed_at"] = now
	case finalization.TerminalStale:
		outcome = "stale"
		job["finalization_outcome"], job["fanout_status"] = "fenced", "fenced"
		job["completed_at"], job["fanout_fenced_at"] = now, now
	case finalization.TerminalDeadLetter:
		status, outcome = deadLetter, "failure"
		job["terminal_at"], job["last_failure_code"] = now, string(cause)
	case finalization.TerminalPending:
		return finalization.ErrInvalid
	}
	delta[status]++
	delta[outcome]++
	job["status"], job["terminal_outcome"] = status, outcome
	job["updated_at"], job["lease_expires_at"] = now, now
	delete(job, "reconcile_after_at")
	if err := addProjection(tx, job, delta); err != nil {
		return err
	}
	return tx.Set(ref, job)
}

func terminal(job document) finalization.TerminalState {
	switch field[string](job, "status") {
	case completed:
		if field[string](job, "finalization_outcome") == "fenced" || field[string](job, "terminal_outcome") == "stale" {
			return finalization.TerminalStale
		}
		return success(job)
	case deadLetter:
		return finalization.TerminalDeadLetter
	default:
		return finalization.TerminalPending
	}
}

func success(job document) finalization.TerminalState {
	if field[bool](job, "go_delivery_dropped") {
		return finalization.TerminalDeliveryDropped
	}
	return finalization.TerminalComplete
}
