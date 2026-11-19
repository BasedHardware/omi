package queue

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue/rules"
)

// Run is one fenced claim of a job, handed to the kind's handler.
type Run struct {
	// Job is the claimed job as of the claim, updated by Save and SetStep.
	Job Job
	// Secret is the live secret a caller presented for a gated job. It is never stored.
	Secret string
	// Preflight is whatever the preflight check returned for this claim.
	Preflight any

	store   *Store
	handler Handler
}

// FinalAttempt reports whether this claim used the job's last transient attempt.
func (r *Run) FinalAttempt() bool { return r.budget().FinalAttempt() }

// WillBudgetRequeue reports whether parking this job now schedules its automatic requeue.
func (r *Run) WillBudgetRequeue() bool {
	return rules.WillRequeue(rules.Requeue{
		Allowed:   r.Job.budgetAllowed,
		Transient: r.Job.intentTransient,
		Gated:     r.Job.Gated,
		Used:      r.Job.BudgetRequeues,
	})
}

// Observe times a named step. Call the returned function when the step ends.
func (r *Run) Observe(step string) func() {
	start := r.store.clock.Now()
	return func() {
		r.store.observer.Step(r.Job.Kind, step, r.store.clock.Now().Sub(start))
	}
}

// Save records progress under the current lease and updates r.Job on success. A nil
// checkpoint only moves the step.
func (r *Run) Save(ctx context.Context, step string, checkpoint json.RawMessage) error {
	if checkpoint == nil {
		return r.SetStep(ctx, step)
	}
	if err := r.transition(ctx, "step=$3,checkpoint=$4", step, checkpoint); err != nil {
		return err
	}
	r.Job.Step = step
	r.Job.Checkpoint = checkpoint
	return nil
}

// SetStep moves the job's step under the current lease.
func (r *Run) SetStep(ctx context.Context, step string) error {
	if r.Job.Step == step {
		return nil
	}
	if err := r.transition(ctx, "step=$3", step); err != nil {
		return err
	}
	r.Job.Step = step
	return nil
}

func (r *Run) budget() rules.Budget {
	return rules.Budget{
		Attempts:              r.Job.Attempts,
		MaxAttempts:           r.store.cfg.MaxAttempts,
		DeterministicAttempts: r.Job.DeterministicAttempts,
		DeterministicMax:      r.store.cfg.DeterministicMax,
		Reconciling:           r.Job.intent != nil,
	}
}

func (r *Run) backoff() time.Duration { return rules.Backoff(r.store.cfg.Backoff, r.Job.Attempts) }

// transition applies set to the job only while this claim still holds an unexpired lease.
// Every write a worker makes goes through here, which is what makes the token a fence.
func (r *Run) transition(ctx context.Context, set string, args ...any) error {
	params := append([]any{r.Job.Key, r.Job.Token}, args...)
	tag, err := r.store.pool.Exec(ctx, "UPDATE queue_jobs SET "+set+`, updated_at=clock_timestamp()
WHERE job_key=$1 AND lease_token=$2 AND state='leased' AND lease_until > clock_timestamp()`, params...)
	if err != nil {
		return fmt.Errorf("transition: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrLease
	}
	return nil
}

func (r *Run) finish(ctx context.Context, state State, result Terminal, cause Cause) error {
	cause = r.store.known(cause)
	var reason *Cause
	if cause != CauseNone {
		reason = &cause
	}
	err := r.transition(ctx, `state=$3,outcome=$4,reason=$5,ready_at=NULL,lease_until=NULL,lane_head=false,
intent=NULL,intent_transient=false`, state, result, reason)
	if err != nil {
		return err
	}
	r.store.observer.Outcome(r.Job.Kind, result, cause)
	r.store.signal()
	return nil
}

const releaseToSchedule = `state=CASE WHEN gated THEN 'blocked' ELSE 'ready' END,
ready_at=CASE WHEN gated THEN clock_timestamp()+$3*interval '1 microsecond' ELSE run_at END,
blocked_since=CASE WHEN gated THEN clock_timestamp() END,lease_until=NULL`

func (r *Run) activate(ctx context.Context) error {
	err := r.transition(ctx, "initializing=false,attempts=attempts-1,reason=NULL,"+releaseToSchedule,
		r.store.cfg.GateTimeout.Microseconds())
	if err != nil {
		return err
	}
	r.store.signal()
	return nil
}

func (r *Run) block(ctx context.Context) error {
	err := r.transition(ctx, `gated=true,initializing=false,attempts=attempts-1,reason=NULL,
state='blocked',ready_at=clock_timestamp()+$3*interval '1 microsecond',
blocked_since=clock_timestamp(),lease_until=NULL`, r.store.cfg.GateTimeout.Microseconds())
	if err != nil {
		return err
	}
	r.store.signal()
	return nil
}

type waitKind uint8

const (
	// waitRefund gives the attempt back: the job was not ready, it did not fail.
	waitRefund waitKind = iota + 1
	// waitTransient spends the attempt on a transient failure.
	waitTransient
	// waitDeterministic spends the attempt and counts a deterministic failure.
	waitDeterministic
)

func (r *Run) wait(ctx context.Context, c Cause, delay time.Duration, kind waitKind) error {
	c = r.store.known(c)
	// A gated job that stops waits for its secret again, not for a timer.
	blocked := r.Job.Gated && r.Job.intent == nil && !r.Job.Initializing
	err := r.transition(ctx, `state=CASE WHEN $6 THEN 'blocked' ELSE 'waiting' END,
reason=$3,lease_until=NULL,
ready_at=clock_timestamp()+(CASE WHEN $6 THEN $8::bigint ELSE $4::bigint END)*interval '1 microsecond',
run_at=CASE WHEN $6 THEN greatest(run_at,clock_timestamp()+$4*interval '1 microsecond') ELSE run_at END,
blocked_since=CASE WHEN $6 THEN clock_timestamp() ELSE blocked_since END,
attempts=attempts-(CASE WHEN $5 THEN 1 ELSE 0 END),
deterministic_attempts=deterministic_attempts+(CASE WHEN $7 THEN 1 ELSE 0 END)`,
		c, delay.Microseconds(), kind == waitRefund, blocked, kind == waitDeterministic,
		r.store.cfg.GateTimeout.Microseconds())
	if err != nil {
		return err
	}
	if kind == waitRefund {
		r.store.observer.Yield(r.Job.Kind, c)
	} else {
		r.store.observer.Retry(r.Job.Kind, c)
	}
	r.store.signal()
	return nil
}

// exhaust records the terminal intent durably before asking the kind to reconcile it, so a
// crash between the two resumes the reconciliation instead of spending another attempt.
func (r *Run) exhaust(ctx context.Context, c Cause, transient bool) error {
	c = r.store.known(c)
	err := r.transition(ctx, `intent=$3,intent_transient=$4,
deterministic_attempts=deterministic_attempts+CASE WHEN $4 THEN 0 ELSE 1 END`, c, transient)
	if err != nil {
		return err
	}
	r.Job.intent = &c
	r.Job.intentTransient = transient
	return r.resolve(ctx)
}

func (r *Run) resolve(ctx context.Context) error {
	return r.handler.Exhausted(ctx, r, *r.Job.intent, r.Job.intentTransient).apply(ctx, r)
}

func (r *Run) park(ctx context.Context) error {
	cause := *r.Job.intent
	if !r.WillBudgetRequeue() {
		return r.finish(ctx, StateParked, TerminalFailure, cause)
	}
	err := r.transition(ctx, `state='parked',reason=$3,lease_until=NULL,lane_head=false,
ready_at=clock_timestamp()+$4*interval '1 microsecond',budget_requeues=budget_requeues+1,
intent=NULL,intent_transient=false`, cause, r.store.cfg.BudgetDelay.Microseconds())
	if err != nil {
		return err
	}
	r.store.observer.BudgetRequeue(cause)
	r.store.signal()
	return nil
}

// execute runs the handler while a second goroutine renews the lease. Losing the lease
// cancels the handler's context, so it stops before it can act on a job it no longer holds.
func (r *Run) execute(ctx context.Context, handler Handler, report func(error)) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	r.handler = handler
	renewed := make(chan struct{})
	go func() {
		defer close(renewed)
		r.renewUntilDone(ctx, cancel, report)
	}()

	var err error
	if r.Job.intent == nil {
		err = handler.Work(ctx, r).apply(ctx, r)
	} else {
		err = r.resolve(ctx)
	}
	if err != nil && !errors.Is(err, ErrLease) && ctx.Err() == nil {
		report(err)
	}
	cancel()
	<-renewed
}

func (r *Run) renewUntilDone(ctx context.Context, cancel context.CancelFunc, report func(error)) {
	job := r.Job
	for {
		select {
		case <-ctx.Done():
			return
		case <-r.store.clock.After(r.store.cfg.Lease / 3):
		}
		if err := r.store.renew(ctx, job); err != nil {
			if ctx.Err() == nil && !errors.Is(err, ErrLease) {
				report(err)
			}
			cancel()
			return
		}
	}
}
