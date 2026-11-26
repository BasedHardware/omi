package queue

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue/rules"
)

// Outcome is what Handler.Work returns. The set is sealed: the constructors below are the
// only way to make one, and each variant carries its own transition, so adding a variant
// forces its author to define what the queue does with it.
type Outcome interface {
	apply(ctx context.Context, r *Run) error
}

type done struct {
	cause      Cause
	step       string
	checkpoint json.RawMessage
}

type retry struct {
	cause Cause
	delay time.Duration
}

type fail struct{ cause Cause }

type yieldMode uint8

const (
	yieldUntilTimer yieldMode = iota + 1
	yieldTenant
	yieldActivate
	yieldForSecret
)

type yield struct {
	cause Cause
	delay time.Duration
	mode  yieldMode
}

type fenced struct{ cause Cause }

type aborted struct{}

// Done finishes the job successfully.
func Done() Outcome { return done{cause: CauseNone} }

// DoneWith finishes the job successfully and records why it ended the way it did.
func DoneWith(c Cause) Outcome { return done{cause: c} }

// DoneAt finishes the job successfully and records its final step and checkpoint in the
// same fenced write, so the last receipt and the completion cannot come apart.
func DoneAt(step string, checkpoint json.RawMessage) Outcome {
	return done{cause: CauseNone, step: step, checkpoint: checkpoint}
}

// Retry reports a transient failure. The job is tried again after the larger of delay and
// the backoff, until the attempt budget is spent.
func Retry(c Cause, delay time.Duration) Outcome { return retry{c, delay} }

// Fail reports a deterministic failure. It is retried a few times, then exhausted.
func Fail(c Cause) Outcome { return fail{c} }

// Yield says the job is not ready. It comes back after delay and the attempt is refunded.
func Yield(c Cause, delay time.Duration) Outcome {
	return yield{cause: c, delay: delay, mode: yieldUntilTimer}
}

// Hold says nothing of this job's tenant should run for now, for example while the tenant
// is being deleted. The job yields, and none of the tenant's jobs is offered until delay
// has passed, so a held tenant costs one claim per delay instead of one per job.
func Hold(c Cause, delay time.Duration) Outcome {
	return yield{cause: c, delay: delay, mode: yieldTenant}
}

// Fence ends the job because its subject left the workflow. Nothing more is done.
func Fence(c Cause) Outcome { return fenced{c} }

// Activate releases an initializing job to its schedule and refunds the claim.
func Activate() Outcome { return yield{mode: yieldActivate} }

// BlockForSecret makes the job gated and refunds the claim. It runs again on Resume.
func BlockForSecret() Outcome { return yield{mode: yieldForSecret} }

// Abort discards the result of a claim that lost its lease or was interrupted.
func Abort() Outcome { return aborted{} }

func (d done) apply(ctx context.Context, r *Run) error {
	if d.step == "" {
		return r.finish(ctx, StateCompleted, TerminalSuccess, d.cause)
	}
	return r.finishAt(ctx, d.step, d.checkpoint)
}

func (f fenced) apply(ctx context.Context, r *Run) error {
	return r.finish(ctx, StateCompleted, TerminalFenced, f.cause)
}

func (aborted) apply(context.Context, *Run) error { return nil }

func (y yield) apply(ctx context.Context, r *Run) error {
	delay := y.delay
	if delay <= 0 {
		delay = r.store.cfg.Backoff
	}
	switch y.mode {
	case yieldActivate:
		return r.activate(ctx)
	case yieldForSecret:
		return r.block(ctx)
	case yieldUntilTimer:
		return r.wait(ctx, y.cause, delay, waitRefund)
	case yieldTenant:
		return r.hold(ctx, y.cause, delay)
	}
	return ErrState
}

func (f fail) apply(ctx context.Context, r *Run) error {
	switch rules.AfterFail(r.budget()) {
	case rules.NextExhaust:
		return r.exhaust(ctx, f.cause, false)
	case rules.NextWait:
		return r.wait(ctx, f.cause, r.backoff(), waitDeterministic)
	}
	return ErrState
}

func (v retry) apply(ctx context.Context, r *Run) error {
	switch rules.AfterRetry(r.budget()) {
	case rules.NextExhaust:
		return r.exhaust(ctx, v.cause, true)
	case rules.NextWait:
		return r.wait(ctx, v.cause, max(r.backoff(), v.delay), waitTransient)
	}
	return ErrState
}

// Classified is implemented by an adapter's error type when the adapter knows what the
// queue should do about the failure.
type Classified interface {
	error
	// Outcome is the queue outcome for this failure.
	Outcome() Outcome
}

type classifiedError struct {
	err     error
	outcome Outcome
}

func (c *classifiedError) Error() string    { return c.err.Error() }
func (c *classifiedError) Unwrap() error    { return c.err }
func (c *classifiedError) Outcome() Outcome { return c.outcome }

// Classify wraps err so that FromError returns outcome for it. An adapter uses it to say
// what a failure means: Classify(err, Retry(CauseVendorDown, 0)). The original error stays
// reachable with errors.Is and errors.As.
func Classify(err error, outcome Outcome) error {
	return &classifiedError{err: err, outcome: outcome}
}

// FromError turns any error from a step into an outcome. A lost lease or a cancelled context
// aborts; a Classified error decides for itself; anything else is retried with fallback as
// its cause, because an unclassified failure is treated as transient, never as success.
func FromError(err error, fallback Cause) Outcome {
	if lost(err) {
		return Abort()
	}
	if classified, ok := errors.AsType[Classified](err); ok {
		return classified.Outcome()
	}
	return Retry(fallback, 0)
}

func lost(err error) bool {
	return errors.Is(err, ErrLease) || errors.Is(err, context.Canceled)
}

// Resolution is what Handler.Exhausted returns. It is a smaller sealed set than Outcome:
// a reconciliation can say what already happened, or ask to look again later. It cannot
// start the job over.
type Resolution interface {
	resolve(ctx context.Context, r *Run) error
}

type later struct {
	cause Cause
	delay time.Duration
}

type parked struct{}

// Resolved finishes the job successfully: the work turned out to be done.
func Resolved() Resolution { return done{cause: CauseNone} }

// ResolvedWith finishes the job successfully and records why it ended the way it did.
func ResolvedWith(c Cause) Resolution { return done{cause: c} }

// Fenced ends the job because its subject left the workflow.
func Fenced(c Cause) Resolution { return fenced{c} }

// Park accepts the failure: the job parks with the cause that exhausted it, or takes its
// single budget requeue when it is entitled to one.
func Park() Resolution { return parked{} }

// Later says the outside state could not be settled yet. The reconciliation runs again
// after the larger of delay and the backoff. It has its own budget, Config.ReconcileMax;
// when that is spent the job parks with CauseReconcileExhausted and keeps its intent.
func Later(c Cause, delay time.Duration) Resolution { return later{c, delay} }

// Dropped discards a reconciliation that lost its lease or was interrupted.
func Dropped() Resolution { return aborted{} }

// LaterOnError turns an error from a reconciliation step into a resolution: a lost lease or
// a cancelled context is dropped, anything else is tried again later with fallback as its
// cause.
func LaterOnError(err error, fallback Cause) Resolution {
	if lost(err) {
		return Dropped()
	}
	return Later(fallback, 0)
}

func (d done) resolve(ctx context.Context, r *Run) error { return d.apply(ctx, r) }

func (f fenced) resolve(ctx context.Context, r *Run) error { return f.apply(ctx, r) }

func (aborted) resolve(context.Context, *Run) error { return nil }

func (parked) resolve(ctx context.Context, r *Run) error { return r.park(ctx) }

func (l later) resolve(ctx context.Context, r *Run) error {
	switch rules.AfterLater(r.job.ReconcileAttempts, r.store.cfg.ReconcileMax) {
	case rules.ReconcileRepair:
		return r.repair(ctx)
	case rules.ReconcileAgain:
		return r.reconcileLater(ctx, l.cause, max(r.backoff(), l.delay))
	}
	return ErrState
}
