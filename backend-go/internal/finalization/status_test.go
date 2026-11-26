package finalization

import (
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestStatusUsesQueueAttemptsAndDispositions(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		state   queue.State
		result  *queue.Terminal
		attempt int
		want    JobStatus
	}{
		{queue.StateReady, nil, 0, JobStatus{"queued", 0, "unknown"}},
		{queue.StateWaiting, nil, 2, JobStatus{"queued", 2, "unknown"}},
		{queue.StateLeased, nil, 3, JobStatus{"leased", 2, "unknown"}},
		{queue.StateParked, new(queue.TerminalFailure), 3, JobStatus{"dead_letter", 3, "failure"}},
		{queue.StateCompleted, new(queue.TerminalSuccess), 3, JobStatus{"completed", 2, "success"}},
		{queue.StateCompleted, new(queue.TerminalFenced), 3, JobStatus{"completed", 2, "stale"}},
	} {
		status, err := projectJobStatus(queue.Job{State: tc.state, Attempts: tc.attempt, Outcome: tc.result})
		if err != nil || status != tc.want {
			t.Errorf("%s status = %+v, %v; want %+v", tc.state, status, err, tc.want)
		}
	}
}
