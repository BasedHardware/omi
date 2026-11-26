package finalization

import (
	"context"
	"errors"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Service admits durable intents and runs ordinary finalization. The binary
// supplies the ports. Admitting and running can be deployed separately.
type Service struct {
	Queue         *queue.Store
	Outbox        Outbox
	Documents     Documents
	Lifecycle     Lifecycle
	Replay        ReplayStore
	Quiet         QuietStore
	Episodes      EpisodePort
	EpisodeIntake EpisodeIntakeStore
	Summaries     SummaryStore
	Meeting       MeetingEvidence
	Batch         BatchCustody
	Gateway       Gateway
	NotesPrompt   NotesPrompt
	Effects       Effects
	Targets       IntegrationTargets
	Integrations  Integrations
}

// Admit commits the outbox before dispatch. If dispatch fails the returned
// intent remains durable and may be dispatched by the outbox reconciler.
func (s *Service) Admit(ctx context.Context, req AdmissionRequest) (Intent, error) {
	if _, ok := rules.ProcessingMode(req.Trigger); !ok || req.Ref.Owner == "" || req.Ref.ID == "" {
		return Intent{}, ErrInvalid
	}
	if (req.RequiresDispatch || req.Trigger == rules.SilentBackfill) && !req.DispatchAvailable {
		return Intent{}, ErrDispatchUnavailable
	}
	if req.Trigger == rules.SilentBackfill && (req.BackfillRunID == "" || req.ExpectedUpdateTime.IsZero() || req.RequiresBYOK) {
		return Intent{}, ErrInvalid
	}
	var intent Intent
	err := s.Queue.Tenant(ctx, req.Ref.Owner, func(scope *queue.Scope) error {
		var err error
		intent, err = s.Outbox.Admit(ctx, scope.Admitting(), req, func(facts rules.AdmissionFacts) rules.AdmissionAction {
			return rules.Admission(req.Trigger, req.RecoveryCutoff, req.RequireExpiredLease, facts)
		})
		if err != nil || intent == (Intent{}) {
			return err
		}
		if intent.Ref != req.Ref {
			return ErrInvalid
		}
		_, err = enqueueIntent(ctx, scope, intent)
		return err
	})
	return intent, err
}

// Dispatch enqueues an already accepted intent. It is safe to repeat after
// either a failed enqueue or a lost dispatch response.
func (s *Service) Dispatch(ctx context.Context, in Intent) (queue.Job, error) {
	var job queue.Job
	err := s.Queue.Tenant(ctx, in.Ref.Owner, func(scope *queue.Scope) error {
		var err error
		job, err = enqueueIntent(ctx, scope, in)
		return err
	})
	return job, err
}

func enqueueIntent(ctx context.Context, scope *queue.Scope, in Intent) (queue.Job, error) {
	newJob, err := in.newJob()
	if err != nil {
		return queue.Job{}, err
	}
	job, _, err := scope.Enqueue(ctx, newJob)
	if err != nil {
		return queue.Job{}, err
	}
	existing, err := readIntent(job)
	if err != nil || job.Kind != Kind || existing != in {
		return queue.Job{}, ErrInvalid
	}
	return job, nil
}

// Work loads the bound row, persists structure, and commits fanout before
// acknowledging queue success.
func (s *Service) Work(ctx context.Context, run *queue.Run) queue.Outcome {
	in, err := readIntent(run.Job())
	if err != nil {
		return queue.Fail(CauseInvalid)
	}
	claim := Claim{Intent: in, Epoch: run.Job().Token, BudgetRequeues: run.Job().BudgetRequeues, LiveBYOK: run.Secret() != ""}
	state, snapshot, err := s.beginWork(ctx, run, claim)
	if err != nil {
		return s.workError(ctx, run, claim, err)
	}
	if outcome := completionOutcome(state); outcome != nil {
		return outcome
	}
	pending, err := s.recoverNotes(ctx, run, claim)
	if err != nil {
		return s.workError(ctx, run, claim, err)
	}
	if snapshot.JobID == "" {
		snapshot, err = s.load(ctx, run, claim)
		if err != nil {
			return s.workError(ctx, run, claim, err)
		}
	}
	finished, err := s.prepareBatch(ctx, run, claim, snapshot)
	if err != nil {
		return s.workError(ctx, run, claim, err)
	}
	if finished {
		return queue.Done()
	}
	if startErr := s.startEpisode(ctx, run, claim, snapshot); startErr != nil {
		return s.workError(ctx, run, claim, startErr)
	}
	var claimed Fanout
	if processErr := s.process(ctx, run, claim, snapshot, pending, &claimed); processErr != nil {
		return s.workError(ctx, run, claim, processErr)
	}
	state, fanoutErr := s.fanout(ctx, run, claim, claimed)
	if fanoutErr != nil {
		return s.workError(ctx, run, claim, fanoutErr)
	}
	if outcome := completionOutcome(state); outcome != nil {
		return outcome
	}
	state, err = s.completion(ctx, run, claim)
	if err != nil {
		return s.workError(ctx, run, claim, err)
	}
	if outcome := completionOutcome(state); outcome != nil {
		return outcome
	}
	return queue.Retry(CauseStore, 0)
}

func completionOutcome(state TerminalState) queue.Outcome {
	switch state {
	case TerminalComplete:
		return queue.Done()
	case TerminalDeliveryDropped:
		return queue.DoneWith(CauseDeliveryDropped)
	case TerminalStale, TerminalDeadLetter:
		return queue.Fence(CauseStale)
	case TerminalPending:
		return nil
	}
	return queue.Fail(CauseInvalid)
}

type guardedRun interface {
	Guard(context.Context, func(context.Context, queue.Guarded) error) error
}

type syncBeginDocuments interface {
	BeginSync(context.Context, queue.Guarded, Claim) (Conversation, bool, error)
}

func (s *Service) beginWork(ctx context.Context, run guardedRun, claim Claim) (TerminalState, Conversation, error) {
	source, available := s.Documents.(syncBeginDocuments)
	if !available || !s.usesServingNotes(claim) {
		state, err := s.begin(ctx, run, claim)
		return state, Conversation{}, err
	}
	var snapshot Conversation
	var reconcile bool
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var err error
		snapshot, reconcile, err = source.BeginSync(ctx, g, claim)
		return err
	})
	if err != nil {
		return TerminalPending, Conversation{}, err
	}
	if reconcile {
		state, err := s.completion(ctx, run, claim)
		return state, Conversation{}, err
	}
	return TerminalPending, snapshot, validateSource(claim, snapshot)
}

func (s *Service) begin(ctx context.Context, run guardedRun, claim Claim) (TerminalState, error) {
	var reconcile bool
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var err error
		reconcile, err = s.Lifecycle.Begin(ctx, g, claim)
		return err
	})
	if err != nil {
		return TerminalPending, err
	}
	if reconcile || claim.Reconcile {
		return s.completion(ctx, run, claim)
	}
	return TerminalPending, nil
}

func (s *Service) completion(ctx context.Context, run guardedRun, claim Claim) (TerminalState, error) {
	var state TerminalState
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var err error
		state, err = s.Lifecycle.ReconcileCompletion(ctx, g, claim)
		return err
	})
	return state, err
}

func (s *Service) workError(ctx context.Context, run *queue.Run, claim Claim, err error) queue.Outcome {
	if !errors.Is(err, ErrStale) {
		return queue.FromError(err, CauseStore)
	}
	state, fenceErr := s.fence(ctx, run, claim)
	if fenceErr != nil {
		return queue.FromError(fenceErr, CauseStore)
	}
	if outcome := completionOutcome(state); outcome != nil {
		return outcome
	}
	return queue.Retry(CauseStore, 0)
}

func (s *Service) fence(ctx context.Context, run guardedRun, claim Claim) (TerminalState, error) {
	var state TerminalState
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var fenceErr error
		state, fenceErr = s.Lifecycle.Fence(ctx, g, claim)
		return fenceErr
	})
	return state, err
}

// Exhausted reconciles a fanout commit before resolving failure. The queue owns
// the delay and accounting for the single automatic budget grant.
func (s *Service) Exhausted(ctx context.Context, run *queue.Reconcile) queue.Resolution {
	in, err := readIntent(run.Job())
	if err != nil {
		return queue.Park()
	}
	claim := Claim{Intent: in, Epoch: run.Job().Token, BudgetRequeues: run.Job().BudgetRequeues, LiveBYOK: run.Secret() != "", Reconcile: true}
	state, err := s.begin(ctx, run, claim)
	if errors.Is(err, ErrStale) {
		state, err = s.completion(ctx, run, claim)
	}
	if err == nil && state == TerminalPending && !run.WillBudgetRequeue() {
		err = run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
			var closeErr error
			state, closeErr = s.Lifecycle.DeadLetter(ctx, g, claim, run.Cause(), run.Transient())
			return closeErr
		})
	}
	if errors.Is(err, ErrStale) {
		state, err = s.fence(ctx, run, claim)
	}
	if err != nil {
		return queue.LaterOnError(err, CauseStore)
	}
	switch state {
	case TerminalComplete:
		return queue.Resolved()
	case TerminalDeliveryDropped:
		return queue.ResolvedWith(CauseDeliveryDropped)
	case TerminalStale:
		return queue.Fenced(CauseStale)
	case TerminalDeadLetter:
		return queue.Park()
	case TerminalPending:
		if run.WillBudgetRequeue() {
			return queue.Park()
		}
	}
	return queue.Later(CauseStore, 0)
}
