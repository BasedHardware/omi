package batchunit

import (
	"context"
	"errors"
	"fmt"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Admitter is what admission needs from the queue.
type Admitter interface {
	Tenant(ctx context.Context, tenant string, fn func(*queue.Scope) error) error
}

// Service admits units and handles their jobs. Every dependency is a field: nothing is
// reached through a global.
type Service struct {
	Queue    Admitter
	Speech   Speech
	Results  Results
	Accounts Accounts
	Observer Observer
	Keys     Keys
}

// Admit enqueues a unit for an owner. Admitting the same unit again returns the first job.
func (s *Service) Admit(ctx context.Context, owner string, unit Unit) (queue.Job, error) {
	job, err := NewJob(s.Keys(owner, unit.ID), owner, unit)
	if err != nil {
		return queue.Job{}, err
	}
	var admitted queue.Job
	err = s.Queue.Tenant(ctx, owner, func(sc *queue.Scope) error {
		fact, admitErr := s.Accounts.Admissible(ctx, sc.Admitting(), owner)
		if admitErr != nil {
			return fmt.Errorf("admit unit: %w", admitErr)
		}
		if fact.Generation != 0 || fact.Exhausted {
			if observeErr := sc.ObserveEntitlement(ctx, fact); observeErr != nil {
				return observeErr
			}
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

// Work transcribes the unit and stores the result, unless a receipt shows that is done.
func (s *Service) Work(ctx context.Context, r *queue.Run) queue.Outcome {
	defer r.Observe(StepSpeech)()
	job := r.Job()
	if _, ok := Stored(job.Checkpoint); ok {
		s.Observer.Transcribed(true)
		return queue.Done()
	}
	input, err := processingInput(job.Meta)
	if err != nil {
		return queue.Fail(CauseInputUnreadable)
	}
	var receipt Receipt
	err = r.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		if runErr := s.Accounts.Runnable(ctx, g, job.Tenant); runErr != nil {
			return runErr
		}
		req := request(g, job, input)
		transcribe := s.Speech.Transcribe
		if input.AlreadyPaid {
			transcribe = s.Speech.Recover
		}
		transcript, callErr := transcribe(ctx, g, req)
		if callErr != nil {
			return callErr
		}
		receipt, callErr = s.Results.Put(ctx, g, req, transcript)
		return callErr
	})
	if err != nil {
		return queue.FromError(err, CauseStepFailed)
	}
	s.Observer.Transcribed(false)
	return s.finish(receipt)
}

// finish records the receipt and completes the job in one fenced write.
func (*Service) finish(receipt Receipt) queue.Outcome {
	checkpoint, err := Checkpoint(receipt)
	if err != nil {
		return queue.Fail(CauseStepFailed)
	}
	return queue.DoneAt(StepStored, checkpoint)
}

// Exhausted settles a job whose attempts ran out. The last attempt may have died after the
// vendor charged and before the receipt was saved, so it asks the vendor what it committed.
// A committed result is stored and the job succeeds; it is never paid for twice and never
// thrown away. With nothing committed, the job parks with the cause that exhausted it.
func (s *Service) Exhausted(ctx context.Context, r *queue.Reconcile) queue.Resolution {
	job := r.Job()
	if _, ok := Stored(job.Checkpoint); ok {
		s.Observer.Transcribed(true)
		return queue.Resolved()
	}
	input, err := processingInput(job.Meta)
	if err != nil {
		return queue.Park()
	}
	var receipt Receipt
	err = r.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		req := request(g, job, input)
		transcript, callErr := s.Speech.Recover(ctx, g, req)
		if callErr != nil {
			return callErr
		}
		receipt, callErr = s.Results.Put(ctx, g, req, transcript)
		return callErr
	})
	if errors.Is(err, ErrNotCommitted) {
		return queue.Park()
	}
	if err != nil {
		return queue.LaterOnError(err, CauseStepFailed)
	}
	checkpoint, err := Checkpoint(receipt)
	if err != nil {
		return queue.Later(CauseStepFailed, 0)
	}
	if err := r.Save(ctx, StepStored, checkpoint); err != nil {
		return queue.LaterOnError(err, CauseStepFailed)
	}
	s.Observer.Transcribed(true)
	return queue.Resolved()
}

func request(g queue.Guarded, job queue.Job, input routedInput) Request {
	return Request{CaptureAt: job.CaptureAt, LateCapture: job.LateCapture, Operation: g.Operation(StepSpeech), Owner: job.Tenant, UnitID: job.Subject, Route: input.Route, BYOK: input.BYOK, Source: Source(input.stored)}
}
