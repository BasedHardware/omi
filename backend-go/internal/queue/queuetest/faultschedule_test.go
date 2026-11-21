package queuetest

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/BasedHardware/omi/backend-go/internal/platform/fault"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type finishHandler struct{}

func (finishHandler) Work(context.Context, *queue.Run) queue.Outcome { return queue.Done() }
func (finishHandler) Exhausted(context.Context, *queue.Reconcile) queue.Resolution {
	return queue.Resolved()
}

func TestSavedClaimFailureScheduleRestartsSeveralWorkers(t *testing.T) {
	t.Parallel()
	data, err := os.ReadFile("../testdata/fault-schedules/claim-restart.json")
	if err != nil {
		t.Fatal(err)
	}
	var schedule fault.Schedule
	err = json.Unmarshal(data, &schedule)
	if err != nil {
		t.Fatal(err)
	}
	policy := Policy()
	policy.Workers = 1
	h := OpenScheduled(t, policy, schedule, queue.Kind{
		Name: "fault_schedule", Formats: []int{1}, Steps: []string{"start"}, Causes: []queue.Cause{"fault"},
	})
	ctx, cancel := context.WithTimeout(context.Background(), limit)
	defer cancel()
	_, err = h.Store.Enqueue(ctx, queue.NewJob{Key: "restart-job", Tenant: "tenant", Kind: "fault_schedule", Format: 1, Step: "start"})
	if err != nil {
		t.Fatal(err)
	}
	h.Start(map[string]queue.Handler{"fault_schedule": finishHandler{}})
	h.Until("restart-job", "first claim committed", func(job queue.Job) bool {
		return job.State == queue.StateLeased && job.Attempts == 1
	})
	waitForInjectedFault(t, h)
	h.Stop()
	job, err := h.Store.Get(ctx, "restart-job")
	if err != nil || job.State != queue.StateLeased || job.Attempts != 1 {
		t.Fatalf("committed fault state = %+v, %v; want one persisted claim", job, err)
	}
	expireLease(t, ctx, h.URL)
	policy.Workers = 4
	h.RestartWithPolicy(policy)
	h.Start(map[string]queue.Handler{"fault_schedule": finishHandler{}})
	job = h.Settled("restart-job")
	if job.Outcome == nil || *job.Outcome != queue.TerminalSuccess || job.Attempts < 2 {
		t.Fatalf("job after restart = %+v, want successful retry", job)
	}
	if h.Faults.Remaining() != 0 || len(h.Faults.History()) != 1 || h.Faults.History()[0] != fault.QueueClaimAfterCommit {
		t.Fatalf("schedule state: remaining=%d history=%v", h.Faults.Remaining(), h.Faults.History())
	}
}

func waitForInjectedFault(t *testing.T, h *Harness) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), limit)
	defer cancel()
	for {
		for _, report := range h.Reports() {
			if errors.Is(report, fault.ErrInjected) {
				return
			}
		}
		select {
		case <-ctx.Done():
			t.Fatalf("fault was not reported: %v", h.Reports())
		case <-time.After(poll):
		}
	}
}

func expireLease(t *testing.T, ctx context.Context, url string) {
	t.Helper()
	conn, err := pgx.Connect(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := conn.Exec(ctx, "UPDATE queue_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE job_key=$1", "restart-job"); err != nil {
		t.Errorf("expire lease: %v", err)
	}
	if err := conn.Close(ctx); err != nil {
		t.Errorf("close lease connection: %v", err)
	}
}
