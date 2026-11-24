package finalizationdocs

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"

	"sync/atomic"
	"testing"

	"google.golang.org/api/option"
	gcs "google.golang.org/api/storage/v1"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func archiveFixture(t *testing.T, serve http.HandlerFunc) GCSArchive {
	t.Helper()
	server := httptest.NewServer(serve)
	t.Cleanup(server.Close)
	client, err := gcs.NewService(t.Context(), option.WithEndpoint(server.URL+"/"), option.WithHTTPClient(server.Client()))
	if err != nil {
		t.Fatal(err)
	}
	return GCSArchive{Objects: client.Objects, Private: "private-fixture", Derived: "regional-fixture"}
}

func TestF19GCSInventoryRefusesRetainedOrIncompletePages(t *testing.T) {
	t.Parallel()
	for _, tt := range []struct {
		name, page string
		code       int
		empty      bool
	}{
		{"empty", "{}", http.StatusOK, true},
		{"retained", `{"items":[{"name":"chunks/owner/conversation/retained"}]}`, http.StatusOK, false},
		{"unavailable", "{}", http.StatusForbidden, false},
		{"unbounded", `{"nextPageToken":"repeat"}`, http.StatusOK, false},
	} {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			var calls atomic.Int64
			archive := archiveFixture(t, func(w http.ResponseWriter, r *http.Request) {
				calls.Add(1)
				q := r.URL.Query()
				if q.Get("prefix") != "chunks/owner/conversation/" || r.URL.Path != "/b/regional-fixture/o" {
					writeFixtureResponse(t, w, "{}")
					return
				}
				if q.Get("pageToken") == "" {
					writeFixtureResponse(t, w, `{"nextPageToken":"next"}`)
					return
				}
				w.WriteHeader(tt.code)
				writeFixtureResponse(t, w, tt.page)
			})
			ref := finalization.Ref{Owner: "owner", ID: "conversation"}
			empty, err := archive.Empty(t.Context(), queue.AdmittingForTest(t, ref.Owner), ref, "session")
			if empty != tt.empty || (err != nil) != (tt.code != http.StatusOK || tt.name == "unbounded") || calls.Load() < 9 {
				t.Fatalf("empty=%v err=%v requests=%d", empty, err, calls.Load())
			}
			before := calls.Load()
			if empty, err := archive.Empty(t.Context(), queue.AdmittingForTest(t, "other"), ref, "session"); empty || err == nil || calls.Load() != before {
				t.Fatal("a mismatched tenant reached storage")
			}
		})
	}
}

func writeFixtureResponse(t *testing.T, w http.ResponseWriter, data string) {
	t.Helper()
	if _, err := fmt.Fprint(w, data); err != nil {
		t.Error(err)
	}
}

// The receiver can observe a successor session publication with the same lease
// deadline while GCS is listing an empty prefix.
func TestF19ArchiveReadFencesRecordingCustodyChanges(t *testing.T) {
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
	path := "users/" + ref.Owner + "/recording_sessions/session"
	session := read(t, bench, path)
	session["lifecycle_sequence"] = int64(2)
	var once sync.Once
	store.Clock = clock.Fixed{T: check.Due}
	store.Archive = archiveFixture(t, func(w http.ResponseWriter, _ *http.Request) {
		once.Do(func() {
			if _, writeErr := bench.Raw.Doc(path).Set(t.Context(), session); writeErr != nil {
				t.Error(writeErr)
			}
		})
		writeFixtureResponse(t, w, "{}")
	})
	wake, err := store.WakeQuiet(t.Context(), a, check)
	if err != nil || wake.Action != rules.QuietRepair || !bench.Exists(t, conversationPath) {
		t.Fatalf("stale storage proof finalized new custody: %v %v", wake.Action, err)
	}
	if got := read(t, bench, path); got["lifecycle_sequence"] != int64(2) || got["lifecycle_phase"] != "in_progress" {
		t.Fatal("stale storage proof changed the recording session")
	}
}
