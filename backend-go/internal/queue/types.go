// Package queue is a durable, fenced job queue on Postgres.
//
// It knows nothing about any job kind. A kind declares itself (its name, formats, steps and
// causes) and supplies a handler; the queue supplies idempotent enqueue, leases with fencing
// tokens, ordered lanes, retries against a durable attempt budget, parking, timers and
// tenant erasure.
package queue

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

// State is where a job is in its life. The set is closed and matches the CHECK constraint
// in migrations/001_queue.sql.
type State string

// The job states.
const (
	// StateReady means the job can be claimed once it is due.
	StateReady State = "ready"
	// StateLeased means a worker holds the job.
	StateLeased State = "leased"
	// StateWaiting means the job is in backoff or yielded until a time.
	StateWaiting State = "waiting"
	// StateBlocked means a gated job is waiting for a caller to present its secret.
	StateBlocked State = "blocked"
	// StateParked means the job stopped on a failure and needs a redrive or its budget requeue.
	StateParked State = "parked"
	// StateCompleted means the job finished, successfully or fenced.
	StateCompleted State = "completed"
)

// States lists every state, for gauges that must report zeros.
func States() []State {
	return []State{StateReady, StateLeased, StateWaiting, StateBlocked, StateParked, StateCompleted}
}

// Cause is a machine-readable reason attached to a retry, a yield, a park or a completion.
//
// The queue owns the few causes below. Every other cause belongs to the kind that returns
// it and must be listed in that Kind's Causes: a cause that is not listed is recorded as
// CauseUnknown, so "unknown" in a metric always means a programming error.
type Cause string

// The causes the queue itself produces.
const (
	// CauseAllowanceExhausted labels the time-only fallback for an unfunded owner.
	CauseAllowanceExhausted Cause = "allowance_exhausted"
	// CauseNone marks a plain success.
	CauseNone Cause = "none"
	// CauseLeaseExpired means the last allowed attempt died while holding the lease.
	CauseLeaseExpired Cause = "lease_expired"
	// CauseHandlerPanic means a handler panicked or returned no outcome. It is retried.
	CauseHandlerPanic Cause = "handler_panic"
	// CauseReconcileExhausted means reconciling a terminal state kept failing. The job is
	// parked with its checkpoint and its original intent kept, for an operator to redrive.
	CauseReconcileExhausted Cause = "reconcile_exhausted"
	// CauseUnknown replaces a cause that no kind declared.
	CauseUnknown Cause = "unknown"
)

// Terminal is how a finished job ended. The set is closed.
type Terminal string

// The terminal outcomes.
const (
	// TerminalSuccess means the work was done.
	TerminalSuccess Terminal = "success"
	// TerminalFailure means the job parked on a failure.
	TerminalFailure Terminal = "failure"
	// TerminalExpiredUnfunded means custody ended while the owner was out of allowance.
	TerminalExpiredUnfunded Terminal = "expired_unfunded"
	// TerminalFenced means the job's subject left the workflow; nothing more was done.
	TerminalFenced Terminal = "fenced"
)

// Terminals lists every terminal outcome.
func Terminals() []Terminal {
	return []Terminal{TerminalSuccess, TerminalFailure, TerminalFenced, TerminalExpiredUnfunded}
}

// Errors a caller can match with errors.Is.
var (
	// ErrAbsent means no such job exists.
	ErrAbsent = errors.New("queue: job absent")
	// ErrErased means the tenant was erased; nothing may be admitted for it.
	ErrErased = errors.New("queue: tenant erased")
	// ErrLease means the caller no longer holds the lease; it must stop and write nothing.
	ErrLease = errors.New("queue: lease lost")
	// ErrState means the job is not in a state that allows the operation.
	ErrState = errors.New("queue: job state conflict")
	// ErrDeferred means the claim was put off by a busy lock.
	ErrDeferred = errors.New("queue: claim deferred")
	// ErrCapacity means too many resumes are already scheduled on this replica.
	ErrCapacity = errors.New("queue: live resume capacity exhausted")
	// ErrStopped means the workers are shutting down and accepted nothing.
	ErrStopped = errors.New("queue: workers stopped")
	// ErrUndeclared means a kind, format, step or handler was used that no Kind declares.
	ErrUndeclared = errors.New("queue: not declared by any kind")
	// ErrConfig means the queue's configuration or kind declarations are invalid.
	ErrConfig = errors.New("queue: invalid configuration")

	errRescheduled = errors.New("queue: job rescheduled")
)

// Job is one row of the queue. Fields without a queue meaning (Meta, Checkpoint) belong to
// the kind. A job never holds payload text, credentials or error text.
type Job struct {
	// Key is the caller's idempotency key and the job's identity.
	Key string
	// Tenant owns the job. Erasing a tenant removes its jobs.
	Tenant string
	// Kind selects the handler.
	Kind string
	// Format is the version of Meta and Checkpoint, fixed at enqueue.
	Format int
	// Subject is what the job is about, for example a conversation id.
	Subject string
	State   State
	// Step is the kind's own progress marker, one of the kind's declared steps.
	Step string
	// Attempts counts claims, including claims by workers that later died.
	Attempts              int
	DeterministicAttempts int
	// ReconcileAttempts counts failed tries at reconciling a terminal state.
	ReconcileAttempts int
	// BudgetRequeues counts automatic requeues spent over the job's lifetime.
	BudgetRequeues int
	// Token is the fencing token of the latest claim. It only grows.
	Token int64
	// Reason is the cause of the latest retry, yield or park; nil when there is none.
	Reason *Cause
	// Outcome is set once the job is terminal.
	Outcome   *Terminal
	CreatedAt time.Time
	UpdatedAt time.Time
	// RunAt is when the job was asked to start.
	RunAt time.Time
	// Meta is the kind's immutable input, fixed by the first enqueue: identifiers and
	// references, never the payload itself.
	Meta json.RawMessage
	// Checkpoint is the kind's saved progress: receipts and references, never the payload.
	Checkpoint json.RawMessage
	// Gated is true for a job that runs only when a caller presents a secret.
	Gated bool
	// Initializing is true until admission finishes binding the job to its subject.
	Initializing bool
	// Ordered is true for a job in an ordered lane.
	Ordered bool
	// CaptureAt and LateCapture identify a paid kind's position relative to committed work at claim.
	CaptureAt       time.Time
	LateCapture     bool
	timedGeneration int64

	budgetAllowed   bool
	intent          *Cause
	intentTransient bool
}

// NewJob is a request to enqueue.
type NewJob struct {
	Key    string
	Tenant string
	Kind   string
	// Format is the version of Meta, one of the kind's declared formats.
	Format  int
	Subject string
	// Step is the kind's starting step.
	Step string
	Meta json.RawMessage
	// Gated makes the job wait for Workers.Resume with a secret before each run. A gated
	// job cannot be ordered.
	Gated bool
	// Initializing holds the job back until Scope.Activate, so admission can bind it first.
	Initializing bool
	// BudgetAllowed opts the job into the single automatic requeue after exhaustion.
	BudgetAllowed bool
	// OrderKey puts the job in an ordered lane: one tenant's jobs of one kind and key run
	// one at a time.
	OrderKey *string
	// OrderAt and SortKey order a lane, then Key breaks ties. SortKey defaults to Key.
	OrderAt time.Time
	SortKey string
	// FundingExempt identifies BYOK or already-paid work of a paid-processing kind.
	FundingExempt bool
	// CustodyDeadline comes from the existing retention policy. It is required to park a unit.
	CustodyDeadline time.Time
	AudioDuration   time.Duration
	// RunAt delays the job. Zero means now.
	RunAt time.Time
}

// Kind declares a job kind. Everything a kind adds to the queue's vocabulary is here, so
// adding a kind is one declaration and one handler, with no edit to the queue.
type Kind struct {
	// Name is the kind's name in job rows and metric labels.
	Name string
	// PaidProcessing opts intake into the owner entitlement condition.
	PaidProcessing bool
	// Formats lists the Meta and Checkpoint versions this binary can run. A job in a format
	// that is not listed is left for a replica that lists it.
	Formats []int
	// Steps lists every step the kind's jobs can be at.
	Steps []string
	// Causes lists every cause the kind's handler can return.
	Causes []Cause
}

// Config is the queue's policy. Every duration and limit a rule needs is here.
type Config struct {
	// TimeOnlyEntitlementHold selects the legacy tenant-wide timer for verified paid-intake refusals.
	TimeOnlyEntitlementHold bool
	// Lease is how long a claim lasts without renewal.
	Lease time.Duration
	// Backoff is the base retry delay.
	Backoff time.Duration
	// BudgetDelay is the wait before the single automatic requeue.
	BudgetDelay time.Duration
	// GateTimeout is how long a gated job waits for its secret before it is abandoned.
	GateTimeout time.Duration
	// GateAbandoned is the cause recorded when GateTimeout passes.
	GateAbandoned Cause
	// MaxAttempts bounds claims per job for transient failures.
	MaxAttempts int
	// DeterministicMax bounds deterministic failures per job.
	DeterministicMax int
	// ReconcileMax bounds failed tries at reconciling a terminal state before the job is
	// parked for an operator.
	ReconcileMax int
	// Workers is the number of jobs one replica runs at once.
	Workers int
}

// Validate reports the first setting that would make the queue misbehave.
func (c Config) Validate() error {
	checks := []struct {
		ok   bool
		what string
	}{
		{c.Lease > 0, "Lease must be positive"},
		{c.Backoff > 0, "Backoff must be positive"},
		{c.BudgetDelay >= 0, "BudgetDelay must not be negative"},
		{c.GateTimeout > 0, "GateTimeout must be positive"},
		{c.GateAbandoned != "", "GateAbandoned must name a cause"},
		{c.MaxAttempts >= 1, "MaxAttempts must be at least 1"},
		{c.DeterministicMax >= 1, "DeterministicMax must be at least 1"},
		{c.ReconcileMax >= 1, "ReconcileMax must be at least 1"},
		{c.Workers >= 1, "Workers must be at least 1"},
	}
	for _, check := range checks {
		if !check.ok {
			return fmt.Errorf("%w: %s", ErrConfig, check.what)
		}
	}
	return nil
}

// Handler is a job kind's behaviour.
type Handler interface {
	// Work advances the job and returns what happened. It must be safe to repeat. A gated
	// job always arrives with its secret, unless it is still initializing.
	Work(ctx context.Context, r *Run) Outcome
	// Exhausted runs after the attempt budget is spent and a terminal intent is recorded.
	// It starts no new work: it finds out what already happened outside the queue, finishes
	// recording it, and returns the final resolution.
	Exhausted(ctx context.Context, r *Reconcile) Resolution
}

// Observer receives the queue's events for metrics. Implementations must not block. Every
// kind, step and cause it receives is declared, or is the literal "unknown".
type Observer interface {
	// EntitlementReleased measures source change to durable release, once per funded owner event.
	EntitlementReleased(time.Duration)
	// Outcome records a terminal result.
	Outcome(kind string, outcome Terminal, cause Cause)
	// Retry records a failed attempt that will be tried again.
	Retry(kind string, cause Cause)
	// Yield records a deferral that refunded its attempt.
	Yield(kind string, cause Cause)
	// BudgetRequeue records the single automatic requeue.
	BudgetRequeue(cause Cause)
	// Step records how long a named step took.
	Step(kind, step string, duration time.Duration)
}
