package finalizationdocs

import (
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func TestF28SummaryScanSharesSchedulerLeaseAndReusesEnrichmentWake(t *testing.T) {
	t.Parallel()
	docs, bench, ref, outbox := summaryFixture(t)
	h := queuetest.Open(t, queuetest.Policy(), finalization.Declaration(Causes()...))
	scan := SummaryScan{Docs: bench.Store, Family: &finalization.Service{Queue: h.Store, Summaries: docs}, Clock: docs.Clock}
	now := docs.Clock.Now()
	put(t, bench, "maintenance/"+summaryCursorID, document{"owner": "other-replica", "lease_until": unix(now.Add(time.Minute))})
	if counts, err := scan.Tick(t.Context()); err != nil || counts != (SummaryScanCounts{}) || bench.Exists(t, outbox) {
		t.Fatalf("active lease did not suppress the repair: %+v %v", counts, err)
	}
	put(t, bench, "maintenance/"+summaryCursorID, document{"owner": "previous", "lease_until": unix(now.Add(-time.Minute))})
	put(t, bench, outbox, document{"wake_generation": int64(2), "summary_expected_revision": int64(4),
		"task_token": "bound", "dispatch": document{"queue": "enrichment"}})
	counts, err := scan.Tick(t.Context())
	if err != nil || counts.Admitted != 1 || counts.Attempted != 1 || counts.Errors != 0 {
		t.Fatalf("due scan: %+v %v", counts, err)
	}
	wake := read(t, bench, outbox)
	if wake["task_token"] != "bound" || wake["wake_generation"] != int64(3) || wake["summary_expected_revision"] != int64(4) ||
		wake["task_due_at"] != unix(now) || !field[bool](wake, "summary_repair") || bench.Exists(t, jobs+"/"+finalization.JobID(ref, 1)) {
		t.Fatal("scan did not hand off the existing enrichment wake")
	}
	scan.Clock = clock.Fixed{T: now.Add(time.Minute)}
	if subsequent, scanErr := scan.Tick(t.Context()); scanErr != nil || subsequent.Admitted != 0 {
		t.Fatalf("scan bypassed its durable interval: %+v %v", subsequent, scanErr)
	}
}
