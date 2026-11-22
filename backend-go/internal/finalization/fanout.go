package finalization

import (
	"context"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func (s *Service) fanout(ctx context.Context, run *queue.Run, claim Claim) error {
	if err := run.SetStep(ctx, StepFanout); err != nil {
		return err
	}
	var fanout Fanout
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var err error
		fanout, err = s.Lifecycle.ClaimFanout(ctx, g, claim)
		return err
	})
	if err != nil {
		return err
	}
	switch fanout.State {
	case FanoutCommitted:
		return nil
	case FanoutStale:
		return ErrStale
	case FanoutAcquired:
		if fanout.Key == "" {
			return queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
		}
	default:
		return queue.Classify(ErrInvalid, queue.Fail(CauseInvalid))
	}
	dropped, err := s.deliver(ctx, run, claim, fanout)
	if err != nil {
		return err
	}
	if commitErr := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		return s.Lifecycle.CompleteFanout(ctx, g, claim, dropped)
	}); commitErr != nil {
		return commitErr
	}
	s.reconcileEpisode(ctx, run, claim, fanout.Conversation)
	return nil
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
		if plan == rules.DeferEffects {
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
