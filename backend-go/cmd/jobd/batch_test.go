package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/conformance/kitstore"
	wire "github.com/BasedHardware/omi/backend-go/internal/conformance/stubapi"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func batchHTTP(t *testing.T, stub http.Handler) (*queuetest.Harness, *api) {
	t.Helper()
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
	accounts := httptest.NewServer(stub)
	t.Cleanup(accounts.Close)
	m := &metrics{}
	client, err := wire.New(accounts.URL, 1, m, clock.System{})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(client.Close)
	units := &batchunit.Service{Queue: h.Store, Accounts: wire.BatchAccounts{Client: client}, Keys: wire.BatchKey, Observer: wire.BatchObserver{Client: client}}
	units.Speech = wire.BatchSpeech{Client: client, Inputs: kit}
	units.Results = wire.BatchResults{Store: kit}
	return h, &api{store: h.Store, kit: kit, units: units}
}

func TestBatchValidatesFundingAuthorityAndCustodyAtIntake(t *testing.T) {
	t.Parallel()
	ctx := t.Context()
	h, server := batchHTTP(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var a wire.Account
		switch r.URL.Path {
		case "/accounts/unversioned-exhausted":
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
	// Even an existing result at the right reference must match the owner and operation.
	for _, tc := range []struct{ id, owner, step string }{
		{"other-owner", "different", batchunit.StepSpeech}, {"other-operation", "held", "other-step"},
	} {
		key := wire.BatchKey("held", tc.id)
		g := queue.GuardedForTest(t, tc.owner, key)
		if err := server.kit.PutResult(ctx, g, key, g.Operation(tc.step), "unrelated"); err != nil {
			t.Fatal(err)
		}
	}
	api := server.routes()
	const base = `{"input":"fixture","order_at":"2026-01-01T00:00:00Z","unit_id":"`
	const duration = `,"duration_seconds":2`
	const deadline = `,"custody_deadline":"2099-01-01T00:00:00Z"`
	for _, tc := range []struct {
		owner, id, fields string
		status            int
		code              string
	}{
		{"unversioned-exhausted", "invalid-source", duration + deadline, 503, "temporarily_unavailable"},
		{"legacy", "unversioned-funded", "", 202, ""},
		{"held", "untrusted-flags", `,"byok":true,"already_paid":true`, 422, "held_unit_requires_custody_deadline_and_positive_duration"},
		{"held", "other-owner", "", 422, "held_unit_requires_custody_deadline_and_positive_duration"},
		{"held", "other-operation", "", 422, "held_unit_requires_custody_deadline_and_positive_duration"},
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
	if err != nil || stats.WaitingOnCustomer.Units != 1 {
		t.Fatalf("expected one versioned held unit: %+v, %v", stats, err)
	}
}

func TestBatchHTTPFundingExemptions(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name       string
		generation int64
		byok       bool
	}{
		{"own-key-unversioned", 0, true}, {"own-key-held", 1, true},
		{"paid-unversioned", 0, false}, {"paid-held", 1, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			ctx := t.Context()
			const owner, unitID = "owner", "unit"
			key := wire.BatchKey(owner, unitID)
			var calls atomic.Int32
			h, server := batchHTTP(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch r.URL.Path {
				case "/accounts/owner":
					if err := json.NewEncoder(w).Encode(wire.Account{AllowanceExhausted: true, EntitlementGeneration: tc.generation, OwnKey: tc.byok}); err != nil {
						t.Error(err)
					}
				case "/speech/unit":
					calls.Add(1)
					var body struct {
						wire.VendorInput
						BYOK bool `json:"byok"`
					}
					if err := json.NewDecoder(r.Body).Decode(&body); err != nil || !body.BYOK || body.Job != key || body.Input != "audio" {
						t.Errorf("unexpected speech request: %+v, %v", body, err)
					}
					if _, err := w.Write([]byte(`{"result":"transcribed"}`)); err != nil {
						t.Error(err)
					}
				default:
					http.NotFound(w, r)
				}
			}))
			wantResult := "transcribed"
			wantCalls := int32(1)
			if !tc.byok {
				wantResult, wantCalls = "previously stored", 0
				g := queue.GuardedForTest(t, owner, key)
				if err := server.kit.PutResult(ctx, g, key, g.Operation(batchunit.StepSpeech), wantResult); err != nil {
					t.Fatal(err)
				}
			}
			response := httptest.NewRecorder()
			req := httptest.NewRequestWithContext(ctx, http.MethodPost, "/v1/batch/owner/units",
				strings.NewReader(`{"unit_id":"unit","input":"audio","order_at":"2026-01-01T00:00:00Z","route":"provider"}`))
			server.routes().ServeHTTP(response, req)
			var admitted jobID
			if response.Code != 202 || json.Unmarshal(response.Body.Bytes(), &admitted) != nil || admitted.ID != key {
				t.Fatalf("admission returned HTTP %d, %s", response.Code, response.Body)
			}
			h.Start(map[string]queue.Handler{batchunit.Kind: server.units})
			done := h.Settled(key)
			receipt, ok := batchunit.Stored(done.Checkpoint)
			if *done.Outcome != queue.TerminalSuccess || !ok || receipt.Result != key || calls.Load() != wantCalls {
				t.Fatalf("outcome %s, receipt %+v, speech calls %d", *done.Outcome, receipt, calls.Load())
			}
			result, err := server.kit.Result(ctx, receipt.Result)
			if err != nil || result != wantResult {
				t.Fatalf("stored result %q, %v", result, err)
			}
		})
	}
}
