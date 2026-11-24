package finalization

import (
	"context"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func (s *Service) fanout(ctx context.Context, run *queue.Run, claim Claim, fanout Fanout) (TerminalState, error) {
	if err := run.SetStep(ctx, StepFanout); err != nil {
		return TerminalPending, err
	}
	if fanout.State != FanoutAcquired {
		err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
			var err error
			fanout, err = s.Lifecycle.ClaimFanout(ctx, g, claim)
			return err
		})
		if err != nil {
			return TerminalPending, err
		}
	}
	switch fanout.State {
	case FanoutCommitted:
		return TerminalPending, nil
	case FanoutStale:
		return TerminalPending, ErrStale
	case FanoutAcquired:
		if fanout.Key == "" {
			return TerminalPending, queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
		}
	default:
		return TerminalPending, queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
	}
	dropped, err := s.finishEffects(ctx, run, claim, fanout)
	if err != nil {
		return TerminalPending, err
	}
	var state TerminalState
	if commitErr := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var err error
		state, err = s.Lifecycle.CompleteFanout(ctx, g, claim, dropped)
		return err
	}); commitErr != nil {
		return TerminalPending, commitErr
	}
	if claim.Intent.Trigger != rules.SyncUpdate {
		s.reconcileEpisode(ctx, run, claim, fanout.Conversation)
	}
	return state, nil
}

type combinedSyncEffects interface {
	ApplyAndReconcile(context.Context, queue.Guarded, Claim, Fanout) (bool, error)
}

func (s *Service) finishEffects(ctx context.Context, run *queue.Run, claim Claim, fanout Fanout) (bool, error) {
	snapshot := fanout.Conversation
	reconcile := claim.Intent.Trigger == rules.SyncUpdate && s.Episodes != nil &&
		!snapshot.RecordingLayer && !snapshot.UntrustedCapture
	if port, ok := s.Effects.(combinedSyncEffects); ok && reconcile &&
		rules.PlanEffects(claim.Intent.Trigger, snapshot.RecordingLayer, snapshot.NoDerivedEffects, snapshot.LazyEffects) == rules.EagerEffects {
		var done bool
		err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
			var err error
			done, err = port.ApplyAndReconcile(ctx, g, claim, fanout)
			return err
		})
		if done || err != nil {
			return false, err
		}
	}
	dropped, err := s.deliver(ctx, run, claim, fanout)
	if err != nil || !reconcile {
		return dropped, err
	}
	bounded, cancel := context.WithTimeout(ctx, EpisodeReconcileTimeout)
	defer cancel()
	return dropped, run.Guard(bounded, func(ctx context.Context, g queue.Guarded) error {
		return s.Episodes.Reconcile(ctx, g, claim, snapshot)
	})
}

func (s *Service) deliver(ctx context.Context, run *queue.Run, claim Claim, fanout Fanout) (bool, error) {
	snapshot := fanout.Conversation
	plan := rules.PlanEffects(claim.Intent.Trigger, snapshot.RecordingLayer, snapshot.NoDerivedEffects, snapshot.LazyEffects)
	if plan == rules.SuppressEffects {
		return false, nil
	}
	event := IntegrationEvent{
		ConversationID: claim.Intent.Ref.ID, Revision: claim.Intent.Revision, FanoutKey: fanout.Key,
	}
	var dropped bool
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		if applyErr := s.Effects.Apply(ctx, g, claim, fanout, plan); applyErr != nil {
			return applyErr
		}
		// Python ordinary sync emits creation only when a discarded row becomes
		// visible. The serving worker does not process already-discarded inputs.
		if plan == rules.DeferEffects || s.usesServingNotes(claim) {
			return nil
		}
		targets, resolveErr := s.Targets.Resolve(ctx, g, claim, snapshot)
		if resolveErr != nil || len(targets) == 0 {
			return resolveErr
		}
		var deliveryErr error
		budget := DeliveryBudget{Attempt: run.Job().Attempts, Epoch: claim.Epoch, Final: run.FinalAttempt()}
		dropped, deliveryErr = s.Integrations.Deliver(ctx, g, event, targets, budget)
		return deliveryErr
	})
	return dropped, err
}
