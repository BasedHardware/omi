package batchunit

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Service admits units and handles their jobs. Every dependency is a field: nothing is
// reached through a global.
type Service struct {
	Store    *queue.Store
	Speech   Speech
	Accounts Accounts
	Observer Observer
	Keys     Keys
	// Fallback is the cause recorded when a step fails with an unclassified error.
	Fallback queue.Cause
}

// Admit enqueues a unit for an owner. Admitting the same unit again returns the first job.
func (s *Service) Admit(ctx context.Context, owner string, unit Unit) (queue.Job, error) {
	job, err := NewJob(s.Keys(owner, unit.ID), owner, unit)
	if err != nil {
		return queue.Job{}, err
	}
	var admitted queue.Job
	err = s.Store.Tenant(ctx, owner, func(sc *queue.Scope) error {
		if admitErr := s.Accounts.Admissible(ctx, owner); admitErr != nil {
			return fmt.Errorf("admit unit: %w", admitErr)
		}
		enqueued, inserted, enqueueErr := sc.Enqueue(ctx, job)
		if enqueueErr != nil {
			return fmt.Errorf("admit unit: %w", enqueueErr)
		}
		admitted = enqueued
		s.Observer.Admitted(!inserted)
		return nil
	})
	return admitted, err
}

// Work transcribes the unit unless a stored result already exists.
func (s *Service) Work(ctx context.Context, r *queue.Run) queue.Outcome {
	defer r.Observe(StepSpeech)()
	if Done(r.Job.Checkpoint) {
		s.Observer.Transcribed(true)
		return queue.Done()
	}
	if err := s.Accounts.Preflight(r.Preflight); err != nil {
		return queue.FromError(err, s.Fallback)
	}
	input, err := Input(r.Job.Meta)
	if err != nil {
		return queue.Fail(CauseInputUnreadable)
	}
	s.Observer.Transcribed(false)
	var result string
	err = r.Guard(ctx, func(ctx context.Context) error {
		transcribed, callErr := s.Speech.Transcribe(ctx, r.Job, input)
		result = transcribed
		return callErr
	})
	if err != nil {
		return queue.FromError(err, s.Fallback)
	}
	stored, err := json.Marshal(result)
	if err != nil {
		return queue.Fail(CauseInputUnreadable)
	}
	if err := r.Save(ctx, StepSpeech, stored); err != nil {
		return queue.FromError(err, s.Fallback)
	}
	return queue.Done()
}

// Exhausted finishes a job whose attempts ran out: successfully if its result was already
// stored before the last attempt died, otherwise parked with the cause that exhausted it.
func (s *Service) Exhausted(_ context.Context, r *queue.Run, cause queue.Cause, _ bool) queue.Outcome {
	if Done(r.Job.Checkpoint) {
		s.Observer.Transcribed(true)
		return queue.Done()
	}
	return queue.Fail(cause)
}
