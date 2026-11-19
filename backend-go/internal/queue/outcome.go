package queue

import (
	"context"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue/rules"
)

// Outcome is what a handler returns. The set is sealed: the five constructors below are the
// only way to make one, and each variant carries its own transition, so adding a variant
// forces its author to define what the queue does with it.
type Outcome interface {
	apply(ctx context.Context, r *Run) error
}

type done struct{ cause Cause }

type retry struct {
	cause Cause
	delay time.Duration
}

type fail struct{ cause Cause }

type yieldMode uint8

const (
	yieldUntilTimer yieldMode = iota + 1
	yieldActivate
	yieldForSecret
)

type yield struct {
	cause Cause
	delay time.Duration
	mode  yieldMode
}

type fenced struct {
	cause    Cause
	obsolete bool
}

// Done finishes the job successfully.
func Done() Outcome { return done{CauseNone} }

// DoneWith finishes the job successfully and records why it ended the way it did.
func DoneWith(c Cause) Outcome { return done{c} }

// Retry reports a transient failure. The job is tried again after the larger of delay and
// the backoff, until the attempt budget is spent.
func Retry(c Cause, delay time.Duration) Outcome { return retry{c, delay} }

// Fail reports a deterministic failure. It is retried a few times, then exhausted.
func Fail(c Cause) Outcome { return fail{c} }

// Yield says the job is not ready. It comes back after delay and the attempt is refunded.
func Yield(c Cause, delay time.Duration) Outcome {
	return yield{cause: c, delay: delay, mode: yieldUntilTimer}
}

// Fence ends the job because its subject left the workflow. Nothing more is done.
func Fence(c Cause) Outcome { return fenced{cause: c} }

// Activate releases an initializing job to its schedule and refunds the claim.
func Activate() Outcome { return yield{mode: yieldActivate} }

// BlockForSecret makes the job gated and refunds the claim. It runs again on Resume.
func BlockForSecret() Outcome { return yield{mode: yieldForSecret} }

// Abort discards the result of a claim that lost its lease or was interrupted.
func Abort() Outcome { return fenced{obsolete: true} }

func (d done) apply(ctx context.Context, r *Run) error {
	return r.finish(ctx, StateCompleted, TerminalSuccess, d.cause)
}

func (f fenced) apply(ctx context.Context, r *Run) error {
	if f.obsolete {
		return nil
	}
	return r.finish(ctx, StateCompleted, TerminalFenced, f.cause)
}

func (y yield) apply(ctx context.Context, r *Run) error {
	switch y.mode {
	case yieldActivate:
		return r.activate(ctx)
	case yieldForSecret:
		return r.block(ctx)
	case yieldUntilTimer:
		delay := y.delay
		if delay <= 0 {
			delay = r.store.cfg.Backoff
		}
		return r.wait(ctx, y.cause, delay, waitRefund)
	}
	return ErrState
}

func (f fail) apply(ctx context.Context, r *Run) error {
	switch rules.AfterFail(r.budget()) {
	case rules.NextPark:
		return r.park(ctx)
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
	case rules.NextPark:
		return r.park(ctx)
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

// FromError turns any error from a step into an outcome. A lost lease or a cancelled context
// aborts; a Classified error decides for itself; anything else is retried with fallback as
// its cause, because an unclassified failure is treated as transient, never as success.
func FromError(err error, fallback Cause) Outcome {
	if errors.Is(err, ErrLease) || errors.Is(err, context.Canceled) {
		return Abort()
	}
	if classified, ok := errors.AsType[Classified](err); ok {
		return classified.Outcome()
	}
	return Retry(fallback, 0)
}
