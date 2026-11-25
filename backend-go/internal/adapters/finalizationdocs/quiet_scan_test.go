package finalizationdocs

import (
	"fmt"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func TestF19DueQuietSchedulerRunsArchiveProofThroughQueueScope(t *testing.T) {
	t.Parallel()
	store, bench, ref := quietFixture(t)
	row := read(t, bench, conversationPath)
	delete(row, "transcript_segments")
	row["record_lane_owner"], row["server_batch_audio_closed"], row["server_batch_audio_received"] = "batch_live_v1", true, false
	row["private_cloud_sync_enabled"] = true
	put(t, bench, "users/"+ref.Owner, document{"private_cloud_sync_enabled": true})
	put(t, bench, conversationPath, row)
	a := queue.AdmittingForTest(t, ref.Owner)
	check, err := store.ArmQuiet(t.Context(), a, ref, 1, false)
	if err != nil {
		t.Fatal(err)
	}
	setRecordingLease(t, bench, ref, store.Clock.Now())
	for i := range quietScanLimit {
		put(t, bench, fmt.Sprintf("%s/other-%d", jobs, i), document{"status": "queued", "reconcile_after_at": store.Clock.Now()})
	}
	store.Clock, store.Archive = clock.Fixed{T: check.Due}, archiveResult(true)
	h := queuetest.Open(t, queuetest.Policy(), finalization.Declaration(Causes()...))
	family := &finalization.Service{Queue: h.Store, Quiet: store}
	scan := QuietScan{Docs: store.Docs, Family: family, Clock: store.Clock}
	for tick := range 3 {
		if failed, tickErr := scan.Tick(t.Context()); tickErr != nil || failed != 0 {
			t.Fatalf("wake dispatch: %v, failures %d", tickErr, failed)
		}
		if tick == 0 && !bench.Exists(t, conversationPath) {
			t.Fatal("first tick exceeded its scan page")
		}
	}
	if bench.Exists(t, conversationPath) || read(t, bench, jobs+"/"+finalization.QuietID(ref))["status"] != quietDone ||
		read(t, bench, jobs+"/other-0")["status"] != "queued" {
		t.Fatal("quiet scan failed to retire the archive wake or touched another job")
	}
}
