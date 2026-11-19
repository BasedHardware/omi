// Package queue is a durable, fenced job queue on Postgres.
//
// It knows nothing about any job kind. A kind supplies a handler and its own vocabulary of
// causes; the queue supplies idempotent enqueue, leases with fencing tokens, ordered lanes,
// retries against a durable attempt budget, parking, timers and tenant erasure.
package queue

import (
	"context"
	"encoding/json"
	"errors"
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
// it and must be listed in Config.Causes: a cause that is not listed is recorded as
// CauseUnknown, so "unknown" in a metric always means a programming error.
type Cause string

// The causes the queue itself produces.
const (
	// CauseNone marks a plain success.
	CauseNone Cause = "none"
	// CauseLeaseExpired means the last allowed attempt died while holding the lease.
	CauseLeaseExpired Cause = "lease_expired"
	// CauseKindUnregistered means no handler is registered for the job's kind.
	CauseKindUnregistered Cause = "kind_unregistered"
	// CauseUnknown replaces a cause that no kind registered.
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
	// TerminalFenced means the job's subject left the workflow; nothing more was done.
	TerminalFenced Terminal = "fenced"
)

// Terminals lists every terminal outcome.
func Terminals() []Terminal { return []Terminal{TerminalSuccess, TerminalFailure, TerminalFenced} }

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
	// ErrDeferred means the claim was put off by the preflight check or a busy lock.
	ErrDeferred = errors.New("queue: claim deferred")
	// ErrCapacity means too many resumes are already scheduled on this replica.
	ErrCapacity = errors.New("queue: live resume capacity exhausted")

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
	// Subject is what the job is about, for example a conversation id.
	Subject string
	State   State
	// Step is the kind's own progress marker.
	Step string
	// Attempts counts claims, including claims by workers that later died.
	Attempts              int
	DeterministicAttempts int
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
	// Meta is the kind's immutable input, fixed by the first enqueue.
	Meta json.RawMessage
	// Checkpoint is the kind's saved progress.
	Checkpoint json.RawMessage
	// Gated is true for a job that runs only when a caller presents a secret.
	Gated bool
	// Initializing is true until admission finishes binding the job to its subject.
	Initializing bool

	budgetAllowed   bool
	intent          *Cause
	intentTransient bool
}

// NewJob is a request to enqueue.
type NewJob struct {
	Key     string
	Tenant  string
	Kind    string
	Subject string
	// Step is the kind's starting step.
	Step string
	Meta json.RawMessage
	// Gated makes the job wait for Workers.Resume with a secret before each run.
	Gated bool
	// Initializing holds the job back until Scope.Activate, so admission can bind it first.
	Initializing bool
	// BudgetAllowed opts the job into the single automatic requeue after exhaustion.
	BudgetAllowed bool
	// OrderKey puts the job in an ordered lane: jobs of one kind and key run one at a time.
	OrderKey *string
	// OrderAt and SortKey order a lane, then Key breaks ties. SortKey defaults to Key.
	OrderAt time.Time
	SortKey string
	// RunAt delays the job. Zero means now.
	RunAt time.Time
}

// Config is the queue's policy. Every duration and limit a rule needs is here.
type Config struct {
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
	// Workers is the number of jobs one replica runs at once.
	Workers int
	// Causes is every cause the registered kinds may return.
	Causes []Cause
}

// Handler is a job kind.
type Handler interface {
	// Work advances the job and returns what happened. It must be safe to repeat.
	Work(ctx context.Context, r *Run) Outcome
	// Exhausted runs after the attempt budget is spent and a terminal intent is recorded.
	// It reconciles any external terminal state and returns the final outcome.
	Exhausted(ctx context.Context, r *Run, cause Cause, transient bool) Outcome
}

// Observer receives the queue's events for metrics. Implementations must not block.
type Observer interface {
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

// Preflight can put off a candidate before a lease is issued, for example while its tenant
// is being deleted. It runs with the tenant and candidate locked and must never call back
// into the Store. data is handed to the handler through Run.Preflight.
type Preflight func(ctx context.Context, job Job) (deferFor time.Duration, data any)
