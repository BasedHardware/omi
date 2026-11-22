package finalizationdocs

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
)

func TestF36HTTPRetractionRequiresAuthoritativeAckBeforeSourceDeletion(t *testing.T) {
	t.Parallel()
	store, bench, a, claim, base := cleanupFixture(t)
	var accept atomic.Bool
	var calls atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		var request mergeRetractionRequest
		if r.URL.Path != mergeRetractionPath || r.Header.Get("Authorization") != "Bearer synthetic-token" ||
			json.NewDecoder(r.Body).Decode(&request) != nil || request.Job != claim.ID ||
			request.Generation != claim.Generation || request.Epoch != claim.Epoch || request.SourceIndex != 1 {
			t.Error("canonical receiver did not get the opaque sealed claim")
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		if !accept.Load() {
			w.WriteHeader(http.StatusConflict)
			writeFixtureResponse(t, w, `{"status":"retraction_fenced"}`)
			return
		}
		writeFixtureResponse(t, w, `{"status":"retracted"}`)
	}))
	t.Cleanup(server.Close)
	client, err := httpx.New(server.URL, 1, time.Second, store.Clock)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(client.Close)
	store.MergeRetraction = HTTPMergeRetraction{Client: client, Bearer: func(context.Context) (string, error) { return "synthetic-token", nil }}
	if retractErr := store.CleanupMergeSource(t.Context(), a, claim, "b"); retractErr == nil || !bench.Exists(t, base+"b") {
		t.Fatal("source was removed without canonical acknowledgement")
	}
	accept.Store(true)
	for range 2 {
		if retractErr := store.CleanupMergeSource(t.Context(), a, claim, "b"); retractErr != nil {
			t.Fatal(retractErr)
		}
	}
	if bench.Exists(t, base+"b") || calls.Load() != 2 {
		t.Fatal("successful replay failed to settle source once")
	}
}
