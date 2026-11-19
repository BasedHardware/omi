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
)

// AfterRetry decides what follows a transient failure of ordinary work.
func AfterRetry(b Budget) Next {
	if b.FinalAttempt() {
		return NextExhaust
	}
	return NextWait
}

// AfterFail decides what follows a deterministic failure of ordinary work.
func AfterFail(b Budget) Next {
	if b.DeterministicAttempts+1 >= b.DeterministicMax || b.FinalAttempt() {
		return NextExhaust
	}
	return NextWait
}

// Reconciling is what the queue does when a reconciliation asks to be tried again later.
type Reconciling uint8

// The possible reconciliation follow-ups.
const (
	// ReconcileAgain schedules another reconciliation after a delay.
	ReconcileAgain Reconciling = iota + 1
	// ReconcileRepair parks the job for an operator, keeping its intent and checkpoint.
	ReconcileRepair
)

// AfterLater decides what follows a reconciliation that could not finish. failed counts
// earlier unfinished reconciliations; limit is the most the job may have in total.
// Reconciliation has its own budget so that an unreadable remote state cannot hold a job,
// and the lane behind it, forever.
func AfterLater(failed, limit int) Reconciling {
	if failed+1 >= limit {
		return ReconcileRepair
	}
	return ReconcileAgain
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
	// Gated is true for a job that runs only on a caller-presented secret.
	Gated bool
	// Initializing is true while admission has not finished binding the job.
	Initializing bool
	// HasSecret is true when this claim carries a live secret.
	HasSecret bool
	// HasIntent is true when a terminal intent is already recorded.
	HasIntent bool
	// Attempts counts claims before this one.
	Attempts int
	// MaxAttempts is the transient limit.
	MaxAttempts int
}

// Claim is what a claim does with the job it selected. The set is closed.
type Claim uint8

// The claim actions.
const (
	// ClaimWork leases the job for ordinary work.
	ClaimWork Claim = iota + 1
	// ClaimReconcile leases the job to reconcile the terminal intent already recorded.
	ClaimReconcile
	// ClaimLeaseExpired leases the job to reconcile: its last allowed attempt died.
	ClaimLeaseExpired
	// ClaimGateAbandoned leases the job to reconcile: its wait for a secret ran out.
	ClaimGateAbandoned
	// ClaimReblock returns a gated job to waiting for its secret without running it: the
	// worker that held the secret died, and the secret died with it.
	ClaimReblock
)

// OnClaim decides what a claim does. The rule that matters most: a gated job that is past
// initialization reaches ordinary work only with a secret. Without one it is reconciled if
// its budget or its wait ran out, and otherwise returned to waiting.
func OnClaim(c Claimed) Claim {
	needsSecret := c.Gated && !c.Initializing && !c.HasSecret
	switch {
	case c.HasIntent:
		return ClaimReconcile
	case c.Leased && c.Attempts >= c.MaxAttempts:
		return ClaimLeaseExpired
	case c.Blocked && needsSecret:
		return ClaimGateAbandoned
	case needsSecret:
		return ClaimReblock
	default:
		return ClaimWork
	}
}

// IdleWait is how long the schedule watcher sleeps after finding nothing to claim.
//
// next is the earliest future due time, zero when nothing is scheduled. overdue is true
// when a job is already due yet could not be claimed (its tenant is deferred, a lock is
// busy, or it sits behind a lane head). The watcher sleeps until next so a timer fires on
// time, and when work is overdue no longer than backoff, which the caller grows with each
// empty claim so that unclaimable work is not polled at the floor. The result is always
// between floor and limit.
func IdleWait(now, next time.Time, overdue bool, floor, backoff, limit time.Duration) time.Duration {
	wait := limit
	if !next.IsZero() {
		wait = min(wait, next.Sub(now))
	}
	if overdue {
		wait = min(wait, backoff)
	}
	return min(limit, max(floor, wait))
}
