package main

import (
	"context"
	"encoding/json"
	"io"
	"maps"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/finalizationdocs"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/llmgateway"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
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
	fixture := &gatewayReplayFixture{rejectFirstGet: true}
	server := httptest.NewServer(fixture.handler(t))
	t.Cleanup(server.Close)
	h, runtime, job, _ := gatewayTestJob(t)
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

func TestF10RecoverCommittedOperationBeforeNewerInput(t *testing.T) {
	t.Parallel()
	h, runtime, job, bench := gatewayTestJob(t)
	fixture := &gatewayReplayFixture{}
	fixture.onPost = func(r *http.Request, key string) {
		persisted, err := h.Store.Get(r.Context(), job.Key)
		if err != nil || !strings.Contains(string(persisted.Checkpoint), key) {
			t.Errorf("gateway UUID did not commit before POST: %v", err)
		}
		const path = "users/gateway-owner/conversations/gateway-conversation"
		doc := bench.Raw.Doc(path)
		current, err := doc.Get(r.Context())
		if err != nil {
			t.Error(err)
			return
		}
		fields := current.Data()
		fields["sync_content_revision"] = int64(2)
		fields["transcript_segments"] = []map[string]any{{"text": "Newer synthetic speech"}}
		if _, err := doc.Set(r.Context(), fields); err != nil {
			t.Error(err)
		}
	}
	server := httptest.NewServer(fixture.handler(t))
	t.Cleanup(server.Close)
	bindGatewayFixture(t, runtime, server.URL, clock.System{})
	h.Start(workerdHandlers(runtime.family))
	waiting := h.Until(job.Key, "a separate sync-revision step", func(row queue.Job) bool {
		return row.State == queue.StateWaiting && row.Reason != nil && *row.Reason == finalization.CauseChanged
	})
	fixture.mu.Lock()
	defer fixture.mu.Unlock()
	if fixture.posts != 1 || fixture.gets != 1 || waiting.Step != finalization.StepLoad {
		t.Fatalf("recovery made %d POSTs and %d GETs, then waited at %q", fixture.posts, fixture.gets, waiting.Step)
	}
}

type gatewayReplayFixture struct {
	mu             sync.Mutex
	key            string
	posts, gets    int
	rejectFirstGet bool
	onPost         func(*http.Request, string)
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
			if f.onPost != nil {
				f.onPost(r, key)
			}
			// The completion committed, but the worker lost the response.
			panic(http.ErrAbortHandler)
		case r.Method == http.MethodGet && r.URL.Path == operations+"/"+key && key != "" && key == f.key:
			f.gets++
			if f.rejectFirstGet && f.gets == 1 {
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
	h, runtime, job, _ := gatewayTestJob(t)
	bindGatewayFixture(t, runtime, server.URL, clock.Fixed{T: job.CreatedAt.Add(29 * 24 * time.Hour)})
	h.Start(workerdHandlers(runtime.family))
	settled := h.Settled(job.Key)
	if settled.Reason == nil || *settled.Reason != llmgateway.CauseExpired {
		t.Fatalf("expected the gateway replay cutoff cause: %+v", settled)
	}
}

type deleteBeforeNotes struct {
	bench docstoretest.Bench
}

func (d deleteBeforeNotes) Wait(ctx context.Context, _ queue.Guarded, claim finalization.Claim, _ finalization.Conversation) (bool, error) {
	ref := claim.Intent.Ref
	_, err := d.bench.Raw.Doc("users/"+ref.Owner+"/deleted_conversations/"+ref.ID).Set(ctx, map[string]any{"conversation_id": ref.ID})
	return false, err
}

func TestF32TombstoneBeforeNotesFencesGatewayDispatch(t *testing.T) {
	t.Parallel()
	h, runtime, job, bench := gatewayTestJob(t)
	runtime.family.Meeting = deleteBeforeNotes{bench: bench}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("delete intent allowed gateway request %s", r.Method)
		http.NotFound(w, r)
	}))
	t.Cleanup(server.Close)
	bindGatewayFixture(t, runtime, server.URL, clock.System{})
	h.Start(workerdHandlers(runtime.family))
	settled := h.Settled(job.Key)
	if settled.Outcome == nil || *settled.Outcome != queue.TerminalFenced {
		t.Fatalf("delete intent did not fence finalization: %+v", settled)
	}
}

// Exercise the worker with Python-generated ciphertext, matching the legacy callback guard.
func TestPL745ForeignOwnerTranscriptPreservesCiphertext(t *testing.T) {
	t.Parallel()
	h, runtime, job, bench := gatewayTestJob(t)
	const path = "users/gateway-owner/conversations/gateway-conversation"
	wire, err := os.ReadFile("../../internal/adapters/conversations/testdata/python_wire.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Rows map[string]map[string]any `json:"rows"`
	}
	if decodeErr := json.Unmarshal(wire, &fixture); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	row := fixture.Rows["enhanced_zlib"]
	ciphertext, ok := row["transcript_segments"].(string)
	if !ok || ciphertext == "" || row["transcript_segments_compressed"] != true ||
		row["data_protection_level"] != "enhanced" {
		t.Fatal("fixture must contain a protected transcript")
	}
	// Use the fixture's master key. Authentication fails because the worker
	// reads the ciphertext under gateway-owner, not its encryption owner.
	clk := clock.System{}
	codec := crypt.New("conversation adapter synthetic fixture key")
	cipherWire, encodeErr := json.Marshal(ciphertext)
	if encodeErr != nil {
		t.Fatal(encodeErr)
	}
	segments, decodeErr := codec.Decode("conversation-fixture-owner", crypt.Transcript{
		Segments: cipherWire, Compressed: true,
	})
	if decodeErr != nil || len(segments) == 0 {
		t.Fatalf("fixture must decode for its original owner: %v", decodeErr)
	}
	wireFinalizationDocuments(runtime.family, finalizationdocs.Store{Docs: bench.Store, Clock: clk, Codec: codec}, nil, true)
	doc := bench.Raw.Doc(path)
	original, err := doc.Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	fields := original.Data()
	notes := map[string]any{"title": "Existing title", "overview": "Existing notes"}
	fields["structured"] = notes
	fields["transcript_segments"] = ciphertext
	fields["transcript_segments_compressed"] = true
	fields["data_protection_level"] = row["data_protection_level"]
	if _, writeErr := doc.Set(t.Context(), fields); writeErr != nil {
		t.Fatal(writeErr)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("unreadable transcript reached gateway: %s", r.Method)
		http.NotFound(w, r)
	}))
	t.Cleanup(server.Close)
	bindGatewayFixture(t, runtime, server.URL, clk)

	// Include retry exhaustion so the terminal write must preserve custody too.
	h.Start(workerdHandlers(runtime.family))
	outcome := h.Settled(job.Key)
	if outcome.Outcome == nil || *outcome.Outcome != queue.TerminalFailure ||
		outcome.Reason == nil || *outcome.Reason != conversations.CauseUnreadable {
		t.Fatalf("expected an unreadable-transcript disposition, got %+v", outcome)
	}
	stored, err := doc.Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	fields = stored.Data()
	storedNotes, hasNotes := fields["structured"].(map[string]any)
	if fields["transcript_segments"] != ciphertext || fields["transcript_segments_compressed"] != true ||
		fields["data_protection_level"] != row["data_protection_level"] || fields["discarded"] == true ||
		fields["go_finalization_notes_input_hash"] != nil || !hasNotes || !maps.Equal(storedNotes, notes) {
		t.Fatal("finalization changed transcript custody or committed summary work")
	}
}

func gatewayTestJob(t *testing.T) (*queuetest.Harness, *finalizationRuntime, queue.Job, docstoretest.Bench) {
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
	return h, &finalizationRuntime{family: family}, job, bench
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
