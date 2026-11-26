package finalization

import (
	"context"
	"errors"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// JobStatus is the queue-owned portion of the existing conversation status projection.
type JobStatus struct {
	Status          string `json:"status"`
	AttemptCount    int    `json:"attempt_count"`
	TerminalOutcome string `json:"terminal_outcome"`
}

// Status resolves the queue projection for this ordinary-sync revision.
func (s *Service) Status(ctx context.Context, ref Ref, revision int64) (JobStatus, error) {
	id := JobID(ref, revision)
	job, err := s.Queue.Get(ctx, id)
	if errors.Is(err, queue.ErrAbsent) {
		return JobStatus{}, ErrStale
	}
	if err != nil {
		return JobStatus{}, err
	}
	intent, err := readIntent(job)
	if err != nil || job.Kind != Kind || intent.Ref != ref || intent.Revision != revision ||
		intent.Trigger != rules.SyncUpdate || intent.RequiresBYOK {
		return JobStatus{}, ErrStale
	}
	return projectJobStatus(job)
}

func projectJobStatus(job queue.Job) (JobStatus, error) {
	status := JobStatus{AttemptCount: job.Attempts, TerminalOutcome: "unknown"}
	switch job.State {
	case queue.StateReady, queue.StateWaiting:
		status.Status = "queued"
	case queue.StateLeased:
		status.Status = "leased"
		// The current claim has not failed. Python exposes failed attempts,
		// while the queue counts all claims, including a first success.
		status.AttemptCount = max(0, job.Attempts-1)
	case queue.StateBlocked:
		status.Status = "blocked_byok"
	case queue.StateParked:
		status.Status, status.TerminalOutcome = "dead_letter", "failure"
	case queue.StateCompleted:
		status.Status = "completed"
		status.AttemptCount = max(0, job.Attempts-1)
		if job.Outcome != nil && *job.Outcome == queue.TerminalFenced {
			status.TerminalOutcome = "stale"
		} else {
			status.TerminalOutcome = "success"
		}
	default:
		return JobStatus{}, ErrInvalid
	}
	return status, nil
}
