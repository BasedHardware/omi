package syncfinalization

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestReferenceBindsEveryCallToJobAndSyncRevision(t *testing.T) {
	t.Parallel()
	var mu sync.Mutex
	var received []request
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/finalization/sync-reference" || r.Method != http.MethodPost ||
			r.Header.Get("Authorization") != "Bearer test-identity" {
			w.WriteHeader(http.StatusForbidden)
			return
		}
		var req request
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		mu.Lock()
		received = append(received, req)
		mu.Unlock()
		body := `{}`
		if req.Step == "targets" {
			body = `{"targets":[{"app_id":"app","url":"https://example.test","owned":true,"body":{"id":"fixture"}}]}`
		}
		if _, err := w.Write([]byte(body)); err != nil {
			t.Error(err)
		}
	}))
	defer server.Close()
	client, clientErr := httpx.New(server.URL, 1, time.Second, clock.System{})
	if clientErr != nil {
		t.Fatal(clientErr)
	}
	defer client.Close()
	adapter := Reference{Client: client, Bearer: func(context.Context) (string, error) { return "test-identity", nil }}
	ref := finalization.Ref{Owner: "owner", ID: "conversation"}
	claim := finalization.Claim{Intent: finalization.Intent{Ref: ref, JobID: finalization.JobID(ref, 2), Revision: 2, Trigger: rules.SyncUpdate}, Epoch: 7}
	guard := queue.GuardedForTest(t, ref.Owner, claim.Intent.JobID)
	row := finalization.Conversation{JobID: claim.Intent.JobID, Revision: 2, SyncRevision: 3}
	for _, epoch := range []int64{7, 8} {
		claim.Epoch = epoch
		if err := adapter.Apply(t.Context(), guard, claim, finalization.Fanout{Conversation: row}, rules.EagerEffects); err != nil {
			t.Fatal(err)
		}
	}
	targets, err := adapter.Resolve(t.Context(), guard, claim, row)
	if err != nil || len(targets) != 1 || !targets[0].OwnedByOwner || !targets[0].Created {
		t.Fatalf("target mapping: %+v, %v", targets, err)
	}
	if _, err := adapter.PrepareNotes(t.Context(), guard, claim, row); err != nil {
		t.Fatal(err)
	}
	claim.Intent.Trigger = rules.ClientFinalize
	if _, err := adapter.Wait(t.Context(), guard, claim, row); !errors.Is(err, finalization.ErrInvalid) {
		t.Fatalf("accepted a foreign producer: %v", err)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(received) != 5 || received[0].QueueEpoch != 7 || received[1].QueueEpoch != 8 ||
		received[0].SyncRevision != 3 || received[0].Operation != received[1].Operation ||
		received[0].Operation == received[2].Operation ||
		received[3].Step != "notes" || received[4].Step != "episode-start" {
		t.Fatalf("unexpected operation binding: %+v", received)
	}
}
