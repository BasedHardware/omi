package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/conformance/kitstore"
	wire "github.com/BasedHardware/omi/backend-go/internal/conformance/stubapi"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func TestBatchValidatesFundingAuthorityAndCustodyAtIntake(t *testing.T) {
	t.Parallel()
	ctx := t.Context()
	h := queuetest.Open(t, queuetest.Policy(), batchunit.Declaration())
	kit, err := kitstore.Open(ctx, h.URL)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(kit.Close)
	if err = kit.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	accounts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var a wire.Account
		switch r.URL.Path {
		case "/accounts/unversioned-exhausted", "/accounts/prior-hold":
			a.AllowanceExhausted = true
		case "/accounts/held":
			a.EntitlementGeneration = 1
			a.AllowanceExhausted = true
		case "/accounts/legacy":
		default:
			http.NotFound(w, r)
			return
		}
		if encErr := json.NewEncoder(w).Encode(a); encErr != nil {
			t.Error(encErr)
		}
	}))
	t.Cleanup(accounts.Close)
	m := &metrics{}
	client, err := wire.New(accounts.URL, 1, m, clock.System{})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(client.Close)
	units := &batchunit.Service{Queue: h.Store, Accounts: wire.BatchAccounts{Client: client}, Keys: wire.BatchKey, Observer: wire.BatchObserver{Client: client}}
	api := (&api{store: h.Store, kit: kit, units: units}).routes()
	if err = h.Store.HoldCondition(ctx, "prior-hold", queue.Entitlement, 3); err != nil {
		t.Fatal(err)
	}
	const base = `{"input":"fixture","order_at":"2026-01-01T00:00:00Z","unit_id":"`
	const duration = `,"duration_seconds":2`
	const deadline = `,"custody_deadline":"2099-01-01T00:00:00Z"`
	for _, tc := range []struct {
		owner, id, fields string
		status            int
		code              string
	}{
		{"unversioned-exhausted", "legacy-exhausted", "", 202, ""},
		{"prior-hold", "existing-hold", duration + deadline, 202, ""},
		{"legacy", "unversioned-funded", "", 202, ""},
		{"held", "no-deadline", duration, 422, "held_unit_requires_custody_deadline_and_positive_duration"},
		{"held", "no-duration", deadline, 422, "held_unit_requires_custody_deadline_and_positive_duration"},
		{"held", "versioned", duration + deadline, 202, ""},
		{"held", "versioned", "", 202, ""}, // A duplicate retains the accepted metadata.
	} {
		response := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(ctx, http.MethodPost, "/v1/batch/"+tc.owner+"/units", strings.NewReader(base+tc.id+`"`+tc.fields+"}"))
		api.ServeHTTP(response, req)
		if response.Code != tc.status {
			t.Fatalf("%s: HTTP %d, body %s", tc.id, response.Code, response.Body)
		}
		if tc.code != "" {
			var body errorBody
			if decErr := json.Unmarshal(response.Body.Bytes(), &body); decErr != nil || body.Error != tc.code {
				t.Fatalf("%s: %s", tc.id, response.Body)
			}
		}
	}
	stats, err := h.Store.Stats(ctx)
	if err != nil || stats.WaitingOnCustomer.Units != 2 {
		t.Fatalf("expected one new and one previously stored owner hold: %+v, %v", stats, err)
	}
}
