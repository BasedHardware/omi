// Package rules holds the queue's decisions as pure functions.
//
// Nothing here reads a clock, a database or a network. The queue gathers the facts, calls
// a rule, and performs what the rule decided. That keeps every scheduling decision
// testable as a table and readable without the code that executes it.
package rules

import "time"

const (
	// backoffCapFactor bounds the delay at this multiple of the base.
	backoffCapFactor = 30
	// backoffMaxShift is the largest doubling exponent that can still be below the cap.
	backoffMaxShift = 5
)

// Backoff is the delay before the next attempt: base doubling per attempt already made,
// capped at 30 times base. attempts counts claims so far, including the one that just failed.
func Backoff(base time.Duration, attempts int) time.Duration {
	shift := min(backoffMaxShift, max(0, attempts-1))
	return base * time.Duration(min(backoffCapFactor, 1<<shift))
}

// Budget is a job's standing against its attempt limits when a step reports a failure.
type Budget struct {
	// Attempts counts claims so far, including the current one.
	Attempts int
	// MaxAttempts is the transient limit.
	MaxAttempts int
	// DeterministicAttempts counts earlier deterministic failures.
	DeterministicAttempts int
	// DeterministicMax is the deterministic limit.
	DeterministicMax int
	// Reconciling is true when the job already holds a durable terminal intent and this
	// claim only reconciles it.
	Reconciling bool
}

// FinalAttempt reports whether the current claim used the last transient attempt.
func (b Budget) FinalAttempt() bool { return b.Attempts >= b.MaxAttempts }

// Next is what the queue does after a failed step. The set is closed.
type Next uint8

// The possible next actions.
const (
	// NextWait schedules another attempt after a delay.
	NextWait Next = iota + 1
	// NextExhaust records a durable terminal intent, then asks the kind to reconcile it.
	NextExhaust
	// NextPark finishes reconciling a terminal intent that is already recorded.
	NextPark
)

// AfterRetry decides what follows a transient failure.
func AfterRetry(b Budget) Next {
	if !b.Reconciling && b.FinalAttempt() {
		return NextExhaust
	}
	return NextWait
}

// AfterFail decides what follows a deterministic failure.
func AfterFail(b Budget) Next {
	switch {
	case b.Reconciling:
		return NextPark
	case b.DeterministicAttempts+1 >= b.DeterministicMax || b.FinalAttempt():
		return NextExhaust
	default:
		return NextWait
	}
}

// Requeue is the facts that decide whether a parked job gets its one automatic requeue.
type Requeue struct {
	// Allowed is the kind's opt-in at enqueue.
	Allowed bool
	// Transient is true when the cause that exhausted the job was transient.
	Transient bool
	// Gated is true for a job that runs only on a caller-presented secret.
	Gated bool
	// Used counts requeues already spent over the job's lifetime.
	Used int
}

// WillRequeue reports whether parking now schedules the single budget requeue.
func WillRequeue(r Requeue) bool {
	return r.Allowed && r.Transient && !r.Gated && r.Used == 0
}

// Claimed is the facts about a job at the moment a worker claims it.
type Claimed struct {
	// Leased is true when the previous holder never released the job.
	Leased bool
	// Blocked is true when the job waits for a caller-presented secret.
	Blocked bool
	// Initializing is true while admission has not finished binding the job.
	Initializing bool
	// HasSecret is true when this claim carries a live secret.
	HasSecret bool
	// Attempts counts claims before this one.
	Attempts int
	// MaxAttempts is the transient limit.
	MaxAttempts int
}

// Recovery is why a claim must reconcile a terminal state instead of doing work.
type Recovery uint8

// The recovery reasons.
const (
	// RecoveryNone means the claim does ordinary work.
	RecoveryNone Recovery = iota
	// RecoveryLeaseExpired means the last allowed attempt died holding the lease.
	RecoveryLeaseExpired
	// RecoveryGateAbandoned means a gated job's wait for a secret ran out.
	RecoveryGateAbandoned
)

// OnClaim decides whether a fresh claim does work or reconciles a terminal state. It applies
// only to a job with no terminal intent recorded yet.
func OnClaim(c Claimed) Recovery {
	switch {
	case c.Leased && c.Attempts >= c.MaxAttempts:
		return RecoveryLeaseExpired
	case c.Blocked && !c.Initializing && !c.HasSecret:
		return RecoveryGateAbandoned
	default:
		return RecoveryNone
	}
}

// IdleWait is how long an idle dispatcher sleeps: until the next job is due, but never
// longer than limit and never shorter than floor. due is zero when nothing is scheduled.
func IdleWait(now, due time.Time, floor, limit time.Duration) time.Duration {
	if due.IsZero() {
		return limit
	}
	return min(limit, max(floor, due.Sub(now)))
}
