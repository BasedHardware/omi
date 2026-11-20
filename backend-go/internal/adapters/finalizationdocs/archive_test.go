package finalizationdocs

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"google.golang.org/api/option"
	gcs "google.golang.org/api/storage/v1"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
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
					writeArchiveResponse(t, w, "{}")
					return
				}
				if q.Get("pageToken") == "" {
					writeArchiveResponse(t, w, `{"nextPageToken":"next"}`)
					return
				}
				w.WriteHeader(tt.code)
				writeArchiveResponse(t, w, tt.page)
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

func writeArchiveResponse(t *testing.T, w http.ResponseWriter, data string) {
	t.Helper()
	if _, err := fmt.Fprint(w, data); err != nil {
		t.Error(err)
	}
}
