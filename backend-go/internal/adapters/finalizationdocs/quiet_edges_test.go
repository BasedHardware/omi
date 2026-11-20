package finalizationdocs

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type archiveResult bool

func (r archiveResult) Empty(_ context.Context, a queue.Admitting, _ finalization.Ref, _ string) (bool, error) {
	return bool(r), a.Err()
}

func TestF19EmptyCleanupRequiresClosedStorageProof(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name  string
		proof bool
		want  rules.QuietAction
	}{
		{"proved-empty", true, rules.QuietRetire},
		{"storage-appeared", false, rules.QuietRepair},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			store, bench, ref := quietFixture(t)
			start := store.Clock.Now()
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
			setRecordingLease(t, bench, ref, start)
			store.Clock, store.Archive = clock.Fixed{T: check.Due}, archiveResult(tc.proof)
			wake, err := store.WakeQuiet(t.Context(), a, check)
			if err != nil || wake.Action != tc.want {
				t.Fatalf("wake: %+v %v", wake, err)
			}
			tombstone := "users/" + ref.Owner + "/deleted_conversations/" + ref.ID
			if bench.Exists(t, benchPath(ref)) == tc.proof || bench.Exists(t, tombstone) != tc.proof {
				t.Fatalf("incorrect deletion with storage proof=%t", tc.proof)
			}
		})
	}
}

func benchPath(ref finalization.Ref) string { return "users/" + ref.Owner + "/conversations/" + ref.ID }

func TestF20OversizeHoldAndCutoffFence(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name   string
		target bool
		cutoff time.Duration
		want   rules.QuietAction
		status string
	}{
		{"different-document", false, -time.Hour, rules.QuietRetire, "in_progress"},
		{"recent-writer", true, -time.Hour, rules.QuietWait, "in_progress"},
		{"quiescent-target", true, time.Hour, rules.QuietRetire, "completed"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			store, bench, ref := quietFixture(t)
			row := read(t, bench, conversationPath)
			row["transcript_segments"] = []document{{"text": strings.Repeat("s", minOversizeBytes)}}
			put(t, bench, conversationPath, row)
			a := queue.AdmittingForTest(t, ref.Owner)
			check, err := store.ArmQuiet(t.Context(), a, ref, 1, false)
			if err != nil {
				t.Fatal(err)
			}
			wake := finalization.QuietWake{Check: check, Cutoff: time.Now().Add(tc.cutoff)}
			var action rules.QuietAction
			err = store.Docs.Fenced(t.Context(), a, ref.Owner, func(tx *docstore.Tx) error {
				var closeErr error
				action, closeErr = resolveQuietLimit(tx, wake, func(docstore.Ref) bool { return tc.target }, true, time.Now().Add(2*time.Hour))
				return closeErr
			})
			if err != nil || action != tc.want || read(t, bench, conversationPath)["status"] != tc.status {
				t.Fatalf("oversize disposition %v, err %v", action, err)
			}
			active := read(t, bench, jobs+"/"+finalization.QuietID(ref))["status"] == quietWaiting
			if active != (tc.want == rules.QuietWait) {
				t.Fatal("cutoff refusal lost the successor")
			}
		})
	}
}
