package queue

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"runtime/debug"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue/rules"
)

// lease is the identity of one claim. It is fixed when the claim is issued and never
// changes, so the heartbeat, every fenced write and every guard use the same values no
// matter what the handler does with its copy of the job.
type lease struct {
	tenant string
	key    string
	token  int64
}

// Run is one fenced claim of a job, handed to the kind's handler.
type Run struct {
	job     Job
	secret  string
	lease   lease
	store   *Store
	handler Handler
}

// Job returns the claimed job as of the claim, with the progress saved since.
func (r *Run) Job() Job { return r.job }

// Secret returns the live secret a caller presented for a gated job. It is never stored.
// It is empty for a job that is not gated and for one that is still initializing.
func (r *Run) Secret() string { return r.secret }

// FinalAttempt reports whether this claim used the job's last transient attempt.
func (r *Run) FinalAttempt() bool { return r.budget().FinalAttempt() }

// Observe times a named step. Call the returned function when the step ends.
func (r *Run) Observe(step string) func() {
	start := r.store.clock.Now()
	label := r.store.kinds.stepLabel(r.job.Kind, step)
	return func() {
		r.store.observer.Step(r.job.Kind, label, r.store.clock.Now().Sub(start))
	}
}

// Save records progress under the current lease. A nil checkpoint only moves the step.
// The checkpoint holds receipts and references, never the payload.
func (r *Run) Save(ctx context.Context, step string, checkpoint json.RawMessage) error {
	if checkpoint == nil {
		return r.SetStep(ctx, step)
	}
	if !r.store.kinds.hasStep(r.job.Kind, step) {
		return fmt.Errorf("%w: step %q of kind %q", ErrUndeclared, step, r.job.Kind)
	}
	if err := r.transition(ctx, "step=$3,checkpoint=$4", step, checkpoint); err != nil {
		return err
	}
	r.job.Step = step
	r.job.Checkpoint = checkpoint
	return nil
}

// SetStep moves the job's step under the current lease.
func (r *Run) SetStep(ctx context.Context, step string) error {
	if r.job.Step == step {
		return nil
	}
	if !r.store.kinds.hasStep(r.job.Kind, step) {
		return fmt.Errorf("%w: step %q of kind %q", ErrUndeclared, step, r.job.Kind)
	}
	if err := r.transition(ctx, "step=$3", step); err != nil {
		return err
	}
	r.job.Step = step
	return nil
}

func (r *Run) willBudgetRequeue() bool {
	return rules.WillRequeue(rules.Requeue{
		Allowed:   r.job.budgetAllowed,
		Transient: r.job.intentTransient,
		Gated:     r.job.Gated,
		Used:      r.job.BudgetRequeues,
	})
}

func (r *Run) budget() rules.Budget {
	return rules.Budget{
		Attempts:              r.job.Attempts,
		MaxAttempts:           r.store.cfg.MaxAttempts,
		DeterministicAttempts: r.job.DeterministicAttempts,
		DeterministicMax:      r.store.cfg.DeterministicMax,
	}
}

func (r *Run) backoff() time.Duration { return rules.Backoff(r.store.cfg.Backoff, r.job.Attempts) }

// transition applies set to the job only while this claim still holds an unexpired lease.
// Every write a worker makes goes through here, which is what makes the token a fence.
func (r *Run) transition(ctx context.Context, set string, args ...any) error {
	params := append([]any{r.lease.key, r.lease.token}, args...)
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
	cause = r.store.kinds.known(cause)
	var reason *Cause
	if cause != CauseNone {
		reason = &cause
	}
	err := r.transition(ctx, `state=$3,outcome=$4,reason=$5,ready_at=NULL,lease_until=NULL,lane_head=false,
intent=NULL,intent_transient=false`, state, result, reason)
	if err != nil {
		return err
	}
	r.store.observer.Outcome(r.job.Kind, result, cause)
	r.store.signal()
	return nil
}

// finishAt completes the job successfully with its final step and checkpoint.
func (r *Run) finishAt(ctx context.Context, step string, checkpoint json.RawMessage) error {
	if !r.store.kinds.hasStep(r.job.Kind, step) {
		return fmt.Errorf("%w: step %q of kind %q", ErrUndeclared, step, r.job.Kind)
	}
	err := r.transition(ctx, `state='completed',outcome='success',reason=NULL,ready_at=NULL,lease_until=NULL,
lane_head=false,intent=NULL,intent_transient=false,step=$3,checkpoint=$4`, step, checkpoint)
	if err != nil {
		return err
	}
	r.store.observer.Outcome(r.job.Kind, TerminalSuccess, CauseNone)
	r.store.signal()
	return nil
}

func (r *Run) activate(ctx context.Context) error {
	err := r.transition(ctx, `initializing=false,attempts=attempts-1,reason=NULL,
state=CASE WHEN gated THEN 'blocked' ELSE 'ready' END,
ready_at=CASE WHEN gated THEN clock_timestamp()+$3*interval '1 microsecond' ELSE run_at END,
blocked_since=CASE WHEN gated THEN clock_timestamp() END,lease_until=NULL`,
		r.store.cfg.GateTimeout.Microseconds())
	if err != nil {
		return err
	}
	r.store.signal()
	return nil
}

func (r *Run) block(ctx context.Context) error {
	if r.job.Ordered {
		return fmt.Errorf("%w: a job in an ordered lane cannot be gated", ErrState)
	}
	err := r.transition(ctx, `gated=true,initializing=false,attempts=attempts-1,reason=NULL,
state='blocked',ready_at=clock_timestamp()+$3*interval '1 microsecond',
blocked_since=clock_timestamp(),lease_until=NULL`, r.store.cfg.GateTimeout.Microseconds())
	if err != nil {
		return err
	}
	r.store.signal()
	return nil
}

// unclaim hands back a claim that never reached a handler: the attempt is refunded and the
// job returns to where it was waiting. It runs during shutdown, so it does not depend on the
// caller's context still being live.
func (r *Run) unclaim(ctx context.Context) error {
	released, err := r.store.releaseClaims(ctx, []lease{r.lease})
	if err == nil && released == 0 {
		return ErrLease
	}
	return err
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
	c = r.store.kinds.known(c)
	// A gated job that stops waits for its secret again, not for a timer.
	blocked := r.job.Gated && !r.job.Initializing
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
		r.store.observer.Yield(r.job.Kind, c)
	} else {
		r.store.observer.Retry(r.job.Kind, c)
	}
	r.store.signal()
	return nil
}

// hold yields the job and keeps every job of its tenant off the schedule for delay.
//
// The tenant is paused first. Releasing the job wakes the dispatchers, and one that woke
// before the pause was recorded could claim another job of the same tenant.
func (r *Run) hold(ctx context.Context, c Cause, delay time.Duration) error {
	_, err := r.store.pool.Exec(ctx, `UPDATE queue_tenants
SET check_after=greatest(check_after,clock_timestamp()+$2*interval '1 microsecond') WHERE uid=$1`,
		r.lease.tenant, delay.Microseconds())
	if err != nil {
		return fmt.Errorf("hold tenant: %w", err)
	}
	return r.wait(ctx, c, delay, waitRefund)
}

// exhaust records the terminal intent durably before asking the kind to reconcile it, so a
// crash between the two resumes the reconciliation instead of spending another attempt.
func (r *Run) exhaust(ctx context.Context, c Cause, transient bool) error {
	c = r.store.kinds.known(c)
	err := r.transition(ctx, `intent=$3,intent_transient=$4,
deterministic_attempts=deterministic_attempts+CASE WHEN $4 THEN 0 ELSE 1 END`, c, transient)
	if err != nil {
		return err
	}
	r.job.intent = &c
	r.job.intentTransient = transient
	return r.reconcile(ctx)
}

func (r *Run) reconcile(ctx context.Context) error {
	resolution := r.handler.Exhausted(ctx, &Reconcile{run: r})
	if resolution == nil {
		return errNoOutcome
	}
	return resolution.resolve(ctx, r)
}

func (r *Run) park(ctx context.Context) error {
	cause := *r.job.intent
	if !r.willBudgetRequeue() {
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

func (r *Run) reconcileLater(ctx context.Context, c Cause, delay time.Duration) error {
	c = r.store.kinds.known(c)
	err := r.transition(ctx, `state='waiting',reason=$3,lease_until=NULL,
ready_at=clock_timestamp()+$4*interval '1 microsecond',reconcile_attempts=reconcile_attempts+1`,
		c, delay.Microseconds())
	if err != nil {
		return err
	}
	r.store.observer.Retry(r.job.Kind, c)
	r.store.signal()
	return nil
}

// repair parks a job whose reconciliation budget is spent. The intent and the checkpoint
// stay on the row, so a redrive resumes the reconciliation instead of starting the work
// over. The lane is released: holding it would stall the tenant on a state that only an
// operator can settle.
func (r *Run) repair(ctx context.Context) error {
	err := r.transition(ctx, `state='parked',outcome='failure',reason=$3,ready_at=NULL,
lease_until=NULL,lane_head=false`, CauseReconcileExhausted)
	if err != nil {
		return err
	}
	r.store.observer.Outcome(r.job.Kind, TerminalFailure, CauseReconcileExhausted)
	r.store.signal()
	return nil
}

var (
	errNoOutcome    = errors.New("queue: handler returned no outcome")
	errHandlerPanic = errors.New("queue: handler panicked")
)

// execute runs the handler while a second goroutine renews the lease. Losing the lease
// cancels the handler's context, so it stops before it can act on a job it no longer holds.
func (r *Run) execute(ctx context.Context, handler Handler, report func(error)) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	r.handler = handler
	renewed := make(chan struct{})
	// The heartbeat gets its own copy of the identity: it never reads the Run.
	identity := r.lease
	go func() {
		defer close(renewed)
		r.store.renewUntilDone(ctx, identity, cancel, report)
	}()

	err := r.step(ctx)
	if err != nil && !errors.Is(err, ErrLease) && ctx.Err() == nil {
		report(fmt.Errorf("kind %s: %w", r.job.Kind, err))
	}
	cancel()
	<-renewed
}

// step runs one handler call and applies its result. A panic or a missing result is a
// transient failure of this job, reported once: it must not take down the replica and the
// other jobs it is running.
func (r *Run) step(ctx context.Context) (err error) {
	defer func() {
		recovered := recover()
		if recovered == nil && !errors.Is(err, errNoOutcome) {
			return
		}
		failure := errNoOutcome
		if recovered != nil {
			// The panic value may hold payload text; the stack does not.
			failure = fmt.Errorf("%w\n%s", errHandlerPanic, debug.Stack())
		}
		err = errors.Join(failure, r.afterCrash(ctx))
	}()
	if r.job.intent != nil {
		return r.reconcile(ctx)
	}
	outcome := r.handler.Work(ctx, r)
	if outcome == nil {
		return errNoOutcome
	}
	return outcome.apply(ctx, r)
}

// afterCrash schedules the job again after a handler crash. The deferred call it runs from
// has already recovered, so a second crash here is a queue bug and is allowed to surface.
func (r *Run) afterCrash(ctx context.Context) error {
	if r.job.intent != nil {
		return Later(CauseHandlerPanic, 0).resolve(ctx, r)
	}
	return r.wait(ctx, CauseHandlerPanic, r.backoff(), waitTransient)
}

func (s *Store) renewUntilDone(ctx context.Context, held lease, cancel context.CancelFunc, report func(error)) {
	for {
		select {
		case <-ctx.Done():
			return
		case <-s.clock.After(s.cfg.Lease / 3):
		}
		if err := s.renew(ctx, held); err != nil {
			if ctx.Err() == nil && !errors.Is(err, ErrLease) {
				report(err)
			}
			cancel()
			return
		}
	}
}

// Reconcile is the claim handed to Handler.Exhausted. It can read the job, save progress
// and make guarded calls to find out and record what already happened. It returns a
// Resolution, which has no way to start the job over.
type Reconcile struct{ run *Run }

// Job returns the claimed job.
func (c *Reconcile) Job() Job { return c.run.job }

// Secret returns the caller's live secret when the claim that exhausted the job carried
// one. It is empty when a later claim reconciles, because a secret is never stored.
func (c *Reconcile) Secret() string { return c.run.secret }

// Cause is the cause that exhausted the job.
func (c *Reconcile) Cause() Cause { return *c.run.job.intent }

// Transient reports whether the cause that exhausted the job was transient.
func (c *Reconcile) Transient() bool { return c.run.job.intentTransient }

// WillBudgetRequeue reports whether Park schedules the job's single automatic requeue
// instead of ending it.
func (c *Reconcile) WillBudgetRequeue() bool { return c.run.willBudgetRequeue() }

// Observe times a named step. Call the returned function when the step ends.
func (c *Reconcile) Observe(step string) func() { return c.run.Observe(step) }

// Save records progress under the current lease.
func (c *Reconcile) Save(ctx context.Context, step string, checkpoint json.RawMessage) error {
	return c.run.Save(ctx, step, checkpoint)
}

// SetStep moves the job's step under the current lease.
func (c *Reconcile) SetStep(ctx context.Context, step string) error { return c.run.SetStep(ctx, step) }

// Guard runs a call to an external system. See Run.Guard.
func (c *Reconcile) Guard(ctx context.Context, fn func(context.Context, Guarded) error) error {
	return c.run.Guard(ctx, fn)
}
