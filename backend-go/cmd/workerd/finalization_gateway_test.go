package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/finalizationdocs"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/llmgateway"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func TestWorkerdFinalizationGatewayIsOptIn(t *testing.T) {
	t.Parallel()
	env := fixtureEnv()
	env["OMI_LLM_GATEWAY_URL"] = "http://127.0.0.1:9080"
	env["LLM_GATEWAY_SERVICE_TOKEN"] = "fixture-token"
	cfg, err := readConfig(envLookup(env), false)
	if err != nil {
		t.Fatal(err)
	}
	runtime := finalizationRuntime{family: &finalization.Service{}}
	if bindErr := runtime.bindFinalizationGateway(cfg.gateway, clock.System{}); bindErr != nil || runtime.family.Gateway != nil {
		t.Fatalf("default configuration bound a gateway: %v", bindErr)
	}

	env["WORKER_FINALIZATION_GATEWAY_ENABLED"] = "true"
	cfg, err = readConfig(envLookup(env), false)
	if err != nil || cfg.gateway.BaseURL != env["OMI_LLM_GATEWAY_URL"] || cfg.gateway.ServiceToken != "fixture-token" {
		t.Fatalf("opt-in did not use the configured URL and legacy token: %v", err)
	}
	env["OMI_LLM_GATEWAY_SERVICE_TOKEN"] = "preferred-token"
	cfg, err = readConfig(envLookup(env), false)
	if err != nil || cfg.gateway.ServiceToken != "preferred-token" {
		t.Fatalf("opt-in did not prefer the canonical service token: %v", err)
	}
	delete(env, "OMI_LLM_GATEWAY_URL")
	if _, err := readConfig(envLookup(env), false); err == nil {
		t.Fatal("opt-in accepted a missing gateway URL")
	}
}

func TestF10WorkerdRecoversNotesThroughKeyedGateway(t *testing.T) {
	t.Parallel()
	fixture := &gatewayReplayFixture{}
	server := httptest.NewServer(fixture.handler(t))
	t.Cleanup(server.Close)
	h, runtime, job := gatewayTestJob(t)
	bindGatewayFixture(t, runtime, server.URL, clock.System{})
	h.Start(workerdHandlers(runtime.family))

	settled := h.Settled(job.Key)
	if settled.Outcome == nil || *settled.Outcome != queue.TerminalSuccess || settled.Attempts != 3 {
		t.Fatalf("want one lost response, one retryable bare 404 and then recovery: %+v", settled)
	}
	fixture.mu.Lock()
	defer fixture.mu.Unlock()
	if fixture.posts != 1 || fixture.gets != 2 {
		t.Fatalf("gateway requests: got %d POSTs and %d GETs, want 1 POST and 2 GETs", fixture.posts, fixture.gets)
	}
}

type gatewayReplayFixture struct {
	mu          sync.Mutex
	key         string
	posts, gets int
}

func (f *gatewayReplayFixture) handler(t *testing.T) http.HandlerFunc {
	t.Helper()
	const operations = "/v1/chat/completions/operations"
	return func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		key := r.Header.Get("X-Omi-Request-Id")
		switch {
		case r.Method == http.MethodPost && r.URL.Path == operations:
			f.posts++
			if f.posts != 1 || len(key) != 36 || r.Header.Get("Idempotency-Key") != key {
				t.Error("POST did not use one keyed submission")
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			f.key = key
			// The completion committed, but the worker lost the response.
			panic(http.ErrAbortHandler)
		case r.Method == http.MethodGet && r.URL.Path == operations+"/"+key && key != "" && key == f.key:
			f.gets++
			if f.gets == 1 {
				http.NotFound(w, r)
				return
			}
			w.Header().Set("X-Omi-Idempotency-Key", key)
			const response = `{"choices":[{"message":{"content":"{\"title\":\"Fixture\",\"overview\":\"Recovered notes\"}"}}]}`
			if _, err := io.WriteString(w, response); err != nil {
				t.Error(err)
			}
		default:
			t.Errorf("unexpected gateway request %s %s", r.Method, r.URL.Path)
			http.NotFound(w, r)
		}
	}
}

func TestF10WorkerdRefusesPaidSubmissionAtOriginalJobCutoff(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("expired paid submission reached gateway: %s", r.Method)
		}
		// Recovery remains read-only after the cutoff. A typed miss lets the
		// worker retry submission, which the original timestamp still fences.
		w.WriteHeader(http.StatusNotFound)
		if _, err := io.WriteString(w, `{"error":{"code":"idempotency_not_found"}}`); err != nil {
			t.Error(err)
		}
	}))
	t.Cleanup(server.Close)
	h, runtime, job := gatewayTestJob(t)
	bindGatewayFixture(t, runtime, server.URL, clock.Fixed{T: job.CreatedAt.Add(29 * 24 * time.Hour)})
	h.Start(workerdHandlers(runtime.family))
	settled := h.Settled(job.Key)
	if settled.Reason == nil || *settled.Reason != llmgateway.CauseExpired {
		t.Fatalf("expected the gateway replay cutoff cause: %+v", settled)
	}
}

func gatewayTestJob(t *testing.T) (*queuetest.Harness, *finalizationRuntime, queue.Job) {
	t.Helper()
	bench := docstoretest.Open(t)
	ref := finalization.Ref{Owner: "gateway-owner", ID: "gateway-conversation"}
	row := map[string]any{
		"status": "in_progress", "transcript_segments": []map[string]any{{"text": "Synthetic capture notes input"}},
	}
	if _, err := bench.Raw.Doc("users/"+ref.Owner+"/conversations/"+ref.ID).Set(t.Context(), row); err != nil {
		t.Fatal(err)
	}
	h := queuetest.Open(t, queuetest.Policy(), workerdKinds()...)
	effects := syntheticEffects{}
	family := &finalization.Service{
		Queue: h.Store, Meeting: effects, Effects: effects, Targets: effects, Batch: effects, Integrations: effects,
	}
	wireFinalizationDocuments(family, finalizationdocs.Store{Docs: bench.Store, Clock: clock.System{}}, nil, true)
	intent, err := family.Admit(t.Context(), finalization.AdmissionRequest{Ref: ref, Trigger: rules.CaptureEnd})
	if err != nil {
		t.Fatal(err)
	}
	job, err := h.Store.Get(t.Context(), intent.JobID)
	if err != nil {
		t.Fatal(err)
	}
	return h, &finalizationRuntime{family: family}, job
}

func bindGatewayFixture(t *testing.T, runtime *finalizationRuntime, baseURL string, clk clock.Clock) {
	t.Helper()
	env := fixtureEnv()
	env["WORKER_FINALIZATION_GATEWAY_ENABLED"] = "true"
	env["OMI_LLM_GATEWAY_URL"] = baseURL
	env["OMI_LLM_GATEWAY_SERVICE_TOKEN"] = "fixture-token"
	cfg, err := readConfig(envLookup(env), false)
	if err != nil {
		t.Fatal(err)
	}
	if err := runtime.bindFinalizationGateway(cfg.gateway, clk); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(runtime.gateway.Close)
	if workerdHandlers(runtime.family)[finalization.Kind] != runtime.family {
		t.Fatal("composed finalization handler was not registered")
	}
}
