package finalization

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

type failedEpisode struct {
	called chan time.Duration
}

func (failedEpisode) Start(_ context.Context, g queue.Guarded, _ Claim, _ Conversation) (bool, error) {
	return false, g.Err()
}

func (e failedEpisode) Reconcile(ctx context.Context, _ queue.Guarded, _ Claim, _ Conversation) error {
	deadline, _ := ctx.Deadline()
	e.called <- time.Until(deadline)
	return errors.New("synthetic episode collaborator failure")
}

func TestF26EpisodeFailureCannotUndoCommittedFanout(t *testing.T) {
	t.Parallel()
	p, req := fixture()
	s, h := setup(t, p, queuetest.Policy())
	called := make(chan time.Duration, 1)
	s.Episodes = failedEpisode{called: called}
	intent := admit(t, s, req)
	h.Start(map[string]queue.Handler{Kind: s})
	job := settled(t, h, intent, queue.TerminalSuccess)
	select {
	case limit := <-called:
		if limit <= 0 || limit > 30*time.Second || job.Attempts != 1 {
			t.Fatalf("episode time bound %v, attempts %d", limit, job.Attempts)
		}
	default:
		t.Fatal("post-fanout episode hook was not called")
	}
}
