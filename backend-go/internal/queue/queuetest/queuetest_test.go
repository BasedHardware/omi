package queuetest_test

import (
	"context"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

type once struct{}

func (once) Work(context.Context, *queue.Run) queue.Outcome               { return queue.Done() }
func (once) Exhausted(context.Context, *queue.Reconcile) queue.Resolution { return queue.Park() }

func TestHarnessRunsAHandlerToATerminalJob(t *testing.T) {
	t.Parallel()
	kind := queue.Kind{Name: "probe", Formats: []int{1}, Steps: []string{"start"}}
	h := queuetest.Open(t, queuetest.Policy(), kind)
	h.Start(map[string]queue.Handler{"probe": once{}})
	job := queue.NewJob{Key: "k", Tenant: "tenant", Kind: "probe", Format: 1, Step: "start"}
	if _, err := h.Store.Enqueue(t.Context(), job); err != nil {
		t.Fatal(err)
	}
	settled := h.Settled("k")
	if *settled.Outcome != queue.TerminalSuccess || settled.Attempts != 1 {
		t.Fatalf("got %+v", settled)
	}
	if reports := h.Reports(); len(reports) != 0 {
		t.Fatalf("unexpected reports: %v", reports)
	}
}
