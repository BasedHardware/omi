package finalizationdocs

import (
	"fmt"
	"reflect"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func summaryFixture(t *testing.T) (Store, docstoretest.Bench, finalization.Ref, string) {
	t.Helper()
	store, bench, req := setup(t)
	put(t, bench, "users/"+req.Ref.Owner, document{"data_protection_level": "standard"})
	put(t, bench, conversationPath, document{
		"status": "completed", "summary_title_provenance": "server_minimum",
		"summary_due_at": int64(2000), "summary_first_pending_at": int64(1800), "sync_content_revision": int64(4),
		"structured": document{"title": "Discussion notes"},
	})
	return store, bench, req.Ref, enrichment + "/" + finalization.QuietID(req.Ref)[len("quiet-"):]
}

func TestF28ConcurrentSummaryRepairReusesTheOutboxAndOldestDeadline(t *testing.T) {
	t.Parallel()
	store, bench, ref, path := summaryFixture(t)
	put(t, bench, path, document{
		"first_pending_at": int64(1700), "summary_deadline_at": int64(1900), "wake_generation": int64(2),
		"summary_expected_revision": int64(4), "task_token": "existing", "dispatch": document{"queue": "fixture"},
	})
	a := queue.AdmittingForTest(t, ref.Owner)
	results := make(chan error, 2)
	for range 2 {
		go func() {
			result, err := store.RepairSummary(t.Context(), a, ref, 0)
			if err == nil && result != rules.SummaryWake {
				err = fmt.Errorf("summary action %v", result)
			}
			results <- err
		}()
	}
	if first, second := <-results, <-results; first != nil || second != nil {
		t.Fatalf("repair: %v %v", first, second)
	}
	outbox := read(t, bench, path)
	if outbox["wake_generation"] != int64(4) || outbox["summary_expected_revision"] != int64(4) ||
		outbox["first_pending_at"] != float64(1700) || outbox["summary_deadline_at"] != float64(1900) ||
		outbox["task_token"] != "existing" || field[string](field[map[string]any](outbox, "dispatch"), "queue") != "fixture" ||
		bench.Exists(t, jobs+"/"+finalization.JobID(ref, 1)) {
		t.Fatalf("inconsistent summary wake: %v", outbox)
	}
}

func TestF28SummaryRepairBlocksBYOKAndParksExpiredDebt(t *testing.T) {
	t.Parallel()
	store, bench, ref, path := summaryFixture(t)
	a := queue.AdmittingForTest(t, ref.Owner)
	put(t, bench, "users/"+ref.Owner, document{"byok": document{"active": true}})
	got, err := store.RepairSummary(t.Context(), a, ref, 0)
	if err != nil || got != rules.SummaryBlockBYOK || bench.Exists(t, path) {
		t.Fatalf("BYOK yielded usable work: %v %v", got, err)
	}
	put(t, bench, "users/"+ref.Owner, document{"byok": document{"active": false}})
	got, err = store.RepairSummary(t.Context(), a, ref, time.Minute)
	if err != nil || got != rules.SummaryPark || !field[bool](read(t, bench, path), "age_gate_parked") {
		t.Fatalf("expired work: %v %v", got, err)
	}
}

func TestSummaryRepairLeavesUnreadableTranscriptParked(t *testing.T) {
	t.Parallel()
	store, bench, ref, path := summaryFixture(t)
	put(t, bench, path, document{
		"uid": ref.Owner, "conversation_id": ref.ID, "version": int64(4),
		"dormant": true, "held_reason": "conversation_unreadable", "due_at": nil, "task_token": "parked",
	})
	before := read(t, bench, path)
	got, err := store.RepairSummary(t.Context(), queue.AdmittingForTest(t, ref.Owner), ref, 0)
	if err != nil || got != rules.SummarySkip {
		t.Fatalf("terminal hold became eligible: %v %v", got, err)
	}
	if after := read(t, bench, path); !reflect.DeepEqual(after, before) {
		t.Fatalf("terminal hold changed: %v", after)
	}
}
