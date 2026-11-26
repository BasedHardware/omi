package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/finalizationdocs"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/llmgateway"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/syncfinalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func TestSyncFinalizationHandlerRunsOnlySeededGoWork(t *testing.T) {
	t.Parallel()
	bench := docstoretest.Open(t)
	h := queuetest.Open(t, queuetest.Policy(), workerdKinds()...)
	var mu sync.Mutex
	steps := make(map[string]int)
	const response = `{"title":"Fixture","overview":"Recorded agenda","sections":[{"heading":"Agenda","body_markdown":"Decide next steps","kind":"main","source_segment_ids":["segment-1","invented"]}]}`

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/chat/completions/operations" && r.Method == http.MethodPost {
			key := r.Header.Get("Idempotency-Key")
			if key == "" || r.Header.Get("X-Omi-User-Uid") != "fixture-owner" {
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			mu.Lock()
			steps["gateway"]++
			mu.Unlock()
			w.Header().Set("X-Omi-Idempotency-Key", key)
			if err := json.NewEncoder(w).Encode(map[string]any{"choices": []map[string]any{
				{"message": map[string]string{"content": response}},
			}}); err != nil {
				t.Error(err)
			}
			return
		}
		var req struct {
			Step         string `json:"step"`
			Conversation string `json:"conversation"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		mu.Lock()
		steps[req.Step]++
		mu.Unlock()
		body := `{"wait":false,"targets":[]}`
		if req.Step == "notes" {
			body = `{"messages":[{"role":"system","text":"Serving notes"},{"role":"user","text":"Fixture evidence"}],
				"terminal_family_enabled":true,
				"episode_checked":true,
				"open_loops_enabled":true,
				"source_projection":{"recorded_start":"2026-01-02T12:00:00Z","recorded_end":"2026-01-02T12:00:48Z",` +
				`"arrival_at":"2026-01-02T12:01:00Z","clock":"device","content_word_units":10,` +
				`"title_evidence":{"prior":"","valid_prior":"","previous_units":0}}}`
			if req.Conversation == "empty-capture" || req.Conversation == "transcript-empty-text" {
				body = `{"episode_checked":true,"minimum":{"title":"","discarded":true,"reason":"empty_transcript","rules_version":5}}`
			}
		}
		if _, err := w.Write([]byte(body)); err != nil {
			t.Error(err)
		}
	}))
	defer server.Close()
	client, clientErr := httpx.New(server.URL, 2, 2*time.Second, clock.System{})
	if clientErr != nil {
		t.Fatal(clientErr)
	}
	defer client.Close()
	runtime := finalizationRuntime{family: &finalization.Service{Queue: h.Store, Integrations: syntheticEffects{}}}
	if err := runtime.bindFinalizationGateway(llmgateway.Config{BaseURL: server.URL, ServiceToken: "fixture-token", Timeout: 2 * time.Second}, clock.System{}); err != nil {
		t.Fatal(err)
	}
	defer runtime.gateway.Close()
	service := runtime.family
	store := finalizationdocs.Store{Docs: bench.Store, Clock: clock.System{}, SyncOnly: true}
	wireFinalizationDocuments(service, store, nil, true)
	wireSyncFinalizationReference(service, syncfinalization.Reference{
		Client: client, Bearer: func(context.Context) (string, error) { return "test-only", nil },
	})
	handlers := workerdHandlers(service)
	if handlers[finalization.Kind] != service {
		t.Fatal("ordinary sync finalization handler did not register")
	}
	ref := finalization.Ref{Owner: "fixture-owner", ID: "fixture-sync"}
	if _, admissionErr := service.Admit(t.Context(), finalization.AdmissionRequest{Ref: ref, Trigger: rules.SyncUpdate}); !errors.Is(admissionErr, finalizationdocs.ErrUnsupported) {
		t.Fatalf("serving composition opened admission: %v", admissionErr)
	}
	cases := []struct {
		id, engine string
		outcome    queue.Terminal
		segments   []map[string]any
	}{
		{"python-owned", "python", queue.TerminalFenced, []map[string]any{}},
		{"worker-owned", "go", queue.TerminalSuccess, []map[string]any{{"id": "segment-1", "text": "Synthetic fixture"}}},
		{"empty-capture", "go", queue.TerminalSuccess, []map[string]any{}},
		{"transcript-empty-text", "go", queue.TerminalSuccess, []map[string]any{{"id": "segment-1", "text": ""}}},
	}
	for _, tc := range cases {
		ref.ID = tc.id
		jobID := finalization.JobID(ref, 1)
		doc := bench.Raw.Doc("users/" + ref.Owner + "/conversations/" + ref.ID)
		if _, err := doc.Set(t.Context(), map[string]any{
			"status": "processing", "finalization_engine": tc.engine, "finalization_owner_epoch": int64(1),
			"finalization_job_id": jobID, "finalization_revision": int64(1), "sync_content_revision": int64(1),
			"summary_title_provenance":   "server_minimum",
			"client_platform":            "ios",
			"folder_id":                  "owner-folder",
			"folder_user_set":            true,
			"processing_conversation_id": "synthetic-processing-id",
			"structured":                 map[string]any{"title_provenance": "server_minimum", "title": "Stand-in"},
			"transcript_segments":        tc.segments,
		}); err != nil {
			t.Fatal(err)
		}
		if _, err := bench.Raw.Doc("conversation_finalization_jobs/"+jobID).Set(t.Context(), map[string]any{
			"status": "queued", "schema_version": int64(1), "finalization_engine": "go", "finalization_owner_epoch": int64(1),
			"uid": ref.Owner, "conversation_id": ref.ID, "finalization_revision": int64(1), "processing_trigger": "sync_update",
		}); err != nil {
			t.Fatal(err)
		}
		if _, err := service.Dispatch(t.Context(), finalization.Intent{
			Ref: ref, JobID: jobID, Revision: 1, Trigger: rules.SyncUpdate,
		}); err != nil {
			t.Fatal(err)
		}
	}
	h.Start(handlers)
	for _, tc := range cases {
		ref.ID = tc.id
		job := h.Settled(finalization.JobID(ref, 1))
		if job.Outcome == nil || *job.Outcome != tc.outcome {
			t.Fatalf("unexpected %s job outcome: %+v", tc.id, job)
		}
	}
	for _, id := range []string{"empty-capture", "transcript-empty-text"} {
		assertEmptySyncDiscard(t, bench, id)
	}
	persisted, err := bench.Raw.Doc("users/fixture-owner/conversations/worker-owned").Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	var row struct {
		Status                 string `firestore:"status"`
		SummaryTitleProvenance string `firestore:"summary_title_provenance"`
		Structured             struct {
			Sections []struct {
				Heading string   `firestore:"heading"`
				Sources []string `firestore:"source_segment_ids"`
			} `firestore:"sections"`
		} `firestore:"structured"`
	}
	if err := persisted.DataTo(&row); err != nil {
		t.Fatal(err)
	}
	data := persisted.Data()
	structured, ok := data["structured"].(map[string]any)
	if !ok || row.Status != "completed" || len(row.Structured.Sections) != 1 ||
		row.SummaryTitleProvenance != "generated" || structured["title_provenance"] != nil {
		t.Fatalf("expected the recorded summary: %+v", row)
	}
	section := row.Structured.Sections[0]
	if section.Heading != "Agenda" || len(section.Sources) != 1 || section.Sources[0] != "segment-1" {
		t.Fatalf("wrong stored section: %+v", section)
	}
	if calendar, present := data["calendar_event"]; !present || calendar != nil {
		t.Fatal("ordinary sync must store explicit null for a missing calendar event")
	}
	if audio, ok := data["audio_files"].([]any); !ok || audio == nil || len(audio) != 0 {
		t.Fatal("ordinary sync must store an explicit empty audio list")
	}
	if data["deferred"] != false || data["client_platform"] != "ios" {
		t.Fatal("ordinary sync must store the false default and preserve the current client platform")
	}
	if data["folder_id"] != "owner-folder" || data["processing_memory_id"] != "synthetic-processing-id" {
		t.Fatal("ordinary sync must preserve the owner's folder and populate the legacy processing alias")
	}
	for _, field := range []string{"capture_group_member_context", "terminal_no_derived_effects"} {
		if value, present := data[field]; !present || value != nil {
			t.Fatalf("ordinary sync must store an explicit null for absent %s", field)
		}
	}
	if data["recorded_end"] != time.Date(2026, 1, 2, 12, 0, 48, 0, time.UTC) ||
		data["clock"] != "device" || data["content_word_units"] != int64(10) {
		t.Fatal("ordinary sync must persist recorded span and units with the notes")
	}
	if data["summary_output_present"] != true || data["summary_discard_receipted"] != false ||
		data["summary_processing_lease_until"] != int64(0) || data["terminal_family"] != "success" {
		t.Fatal("ordinary sync must record summary delivery and terminal success")
	}
	if _, ok := data["notes_written_at"].(time.Time); !ok {
		t.Fatal("ordinary sync must record when notes were written")
	}
	if data["title_content_units"] != int64(10) || data["title_change_reason"] != "initial_title" ||
		data["title_changed_at"] != data["notes_written_at"] {
		t.Fatal("ordinary sync must persist the title basis and change alongside the notes")
	}
	for _, key := range []string{"open_loop_extractions", "open_loop_extractions_compressed"} {
		if value, present := data[key]; !present || value != nil {
			t.Fatalf("fresh notes with no extractions must clear %s", key)
		}
	}
	if _, ok := data["summary_completed_at"].(float64); !ok {
		t.Fatal("ordinary sync must record the first summary completion as epoch seconds")
	}
	mu.Lock()
	defer mu.Unlock()
	for _, step := range []string{"gateway", "effects"} {
		if steps[step] != 1 {
			t.Fatalf("expected exactly one call to %s: %v", step, steps)
		}
	}
	if steps["meeting"] != 0 {
		t.Fatalf("ordinary sync must not call the capture-end meeting probe: %v", steps)
	}
	if steps["episode-start"] != 0 {
		t.Fatalf("notes planning must handle the episode check: %v", steps)
	}
	for _, step := range []string{"notes", "episode-reconcile"} {
		if steps[step] != 3 {
			t.Fatalf("expected one call to %s per Go-owned row: %v", step, steps)
		}
	}
	if steps["targets"] != 0 {
		t.Fatal("ordinary sync must not resolve conversation-created recipients")
	}
}

func assertEmptySyncDiscard(t *testing.T, bench docstoretest.Bench, id string) {
	t.Helper()
	row, err := bench.Raw.Doc("users/fixture-owner/conversations/" + id).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	data := row.Data()
	decision, ok := data["relevance_decision"].(map[string]any)
	if !ok || data["status"] != "completed" || data["discarded"] != true ||
		data["summary_discard_receipted"] != true || decision["reason"] != "empty_transcript" {
		t.Fatalf("%s must finish with Python's empty-transcript discard and summary receipt", id)
	}
}
