package llmgateway

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const okCompletion = `{"id":"test","choices":[{"index":0,"finish_reason":"stop","message":{"role":"assistant","content":"{\"title\":\"Example\"}"}}],"usage":{"prompt_tokens":20,"completion_tokens":5}}`

func testClient(t *testing.T, handler http.Handler) Replayable {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set(idempotencyAck, r.Header.Get("X-Omi-Request-Id"))
		handler.ServeHTTP(w, r)
	}))
	t.Cleanup(server.Close)
	return dialTestGateway(t, server.URL, clock.System{})
}

func dialTestGateway(t *testing.T, baseURL string, c clock.Clock) Replayable {
	t.Helper()
	client, err := New(Config{BaseURL: baseURL, ServiceToken: " test-service ", Timeout: 5 * time.Second}, c)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(client.Close)
	return client
}

func writeResponse(t *testing.T, w http.ResponseWriter, status int, body string) {
	t.Helper()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if _, err := w.Write([]byte(body)); err != nil {
		t.Error(err)
	}
}

func prompt() Request {
	return Request{
		Step: "notes", JobCreatedAt: clock.System{}.Now(), Feature: ConversationStructure,
		Messages: []Message{{Role: "user", Text: "test prompt"}},
	}
}

func TestCompleteSendsFeatureLaneAndAccounting(t *testing.T) {
	t.Parallel()
	tests := []struct {
		feature Feature
		lane    string
	}{
		{ConversationStructure, "omi:auto:conv-structure"},
		{ConversationDiscard, "omi:auto:conv-discard"},
		{ConversationActions, "omi:auto:conv-action-items"},
		{ConversationFolder, "omi:auto:conv-folder"},
		{ConversationAppSelect, "omi:auto:conv-app-select"},
		{ConversationAppResult, "omi:auto:conv-app-result"},
		{ConversationV3Summary, "omi:auto:conversation-v3-summary"},
		{ExternalStructure, "omi:auto:external-structure"},
		{Memories, "omi:auto:memories"},
		{MemoryL1, "omi:auto:memory-l1"},
	}
	for _, tc := range tests {
		t.Run(string(tc.feature), func(t *testing.T) {
			t.Parallel()
			client := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != http.MethodPost || r.URL.Path != "/v1/chat/completions/operations" {
					t.Errorf("unexpected route: %s %s", r.Method, r.URL.Path)
				}
				feature := tc.feature
				if feature == MemoryL1 {
					feature = Memories
				}
				if feature == ExternalStructure || feature == ConversationV3Summary {
					feature = ConversationStructure
				}
				if feature == ConversationAppResult || feature == ConversationAppSelect {
					feature = ConversationApps
				}
				wantHeaders := map[string]string{
					"Authorization":        "Bearer test-service",
					"Content-Type":         "application/json",
					"X-Omi-Service-Caller": "backend",
					"X-Omi-User-Uid":       "test-owner",
					"X-Omi-LLM-Feature":    string(feature),
					"X-Omi-App-Platform":   "mobile",
				}
				for name, want := range wantHeaders {
					if got := r.Header.Get(name); got != want {
						t.Errorf("%s = %q, want %q", name, got, want)
					}
				}
				var body completionRequest
				if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
					t.Error(err)
				}
				if body.Model != tc.lane || body.Stream || body.ResponseFormat != nil ||
					body.Metadata.Feature != feature || len(body.Messages) != 1 ||
					body.Messages[0] != (message{Role: "user", Content: "test prompt"}) {
					t.Errorf("unexpected payload: %+v", body)
				}
				writeResponse(t, w, http.StatusOK, okCompletion)
			}))
			in := prompt()
			in.Feature, in.AppPlatform = tc.feature, " Mobile "
			if tc.feature == MemoryL1 {
				in.UsageFeature = MemoryL1
			}
			got, err := client.Complete(t.Context(), queue.GuardedForTest(t, "test-owner", "job"), in)
			if err != nil || got != `{"title":"Example"}` {
				t.Fatalf("Complete = %q, %v", got, err)
			}
		})
	}
}

func TestStructuredBundlesUseStrictSchemaAndVersionMetadata(t *testing.T) {
	t.Parallel()
	tests := []struct {
		feature Feature
		name    string
	}{
		{StructureShadow, "ConversationStructureExtraction"},
		{ActionsShadow, "ActionItemsExtraction"},
	}
	for _, tc := range tests {
		t.Run(string(tc.feature), func(t *testing.T) {
			t.Parallel()
			schema := `{"type":"object","properties":{"title":{"type":"string"}},"required":["title"],"additionalProperties":false}`
			client := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				var body completionRequest
				if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
					t.Error(err)
				}
				if body.Model != "omi:auto:chat-structured" ||
					body.Metadata != (metadata{tc.feature, string(tc.feature) + ".v1", tc.name + ".v1"}) ||
					body.ResponseFormat == nil || body.ResponseFormat.Type != "json_schema" ||
					body.ResponseFormat.JSONSchema.Name != tc.name || !body.ResponseFormat.JSONSchema.Strict ||
					string(body.ResponseFormat.JSONSchema.Schema) != schema {
					t.Errorf("unexpected structured request: %+v", body)
				}
				writeResponse(t, w, http.StatusOK, okCompletion)
			}))
			in := prompt()
			in.Feature, in.Schema = tc.feature, &StrictSchema{Name: tc.name, JSON: []byte(schema)}
			if _, err := client.Complete(t.Context(), queue.GuardedForTest(t, "owner", "job"), in); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestOperationIDSurvivesReplayAndSeparatesJobsAndSteps(t *testing.T) {
	t.Parallel()
	ids := make(chan string, 4)
	client := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := r.Header.Get(idempotencyHeader)
		if key != r.Header.Get("X-Omi-Request-Id") {
			t.Error("key and correlation ID differ")
		}
		ids <- key
		writeResponse(t, w, http.StatusOK, okCompletion)
	}))
	for _, item := range []struct{ job, step string }{
		{"job", "notes"}, {"job", "notes"}, {"job", "memories"}, {"other", "notes"},
	} {
		in := prompt()
		in.Step = item.step
		if _, err := client.Complete(t.Context(), queue.GuardedForTest(t, "owner", item.job), in); err != nil {
			t.Fatal(err)
		}
	}
	first, replay, otherStep, otherJob := <-ids, <-ids, <-ids, <-ids
	if first != replay || first == otherStep || first == otherJob || otherStep == otherJob {
		t.Fatalf("unexpected request IDs: %q %q %q %q", first, replay, otherStep, otherJob)
	}
	if first != "d2241ab4-95e3-880b-bda8-23f7e5334859" {
		t.Fatalf("request ID derivation changed: %q", first)
	}
}

func TestInvalidRequestsDoNotCallGateway(t *testing.T) {
	t.Parallel()
	client := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Error("unexpected paid call")
		writeResponse(t, w, http.StatusOK, okCompletion)
	}))
	guard := queue.GuardedForTest(t, "owner", "job")
	var dead queue.Guarded
	if _, err := client.Complete(t.Context(), dead, prompt()); !errors.Is(err, queue.ErrLease) {
		t.Fatalf("Complete without guard = %v", err)
	}
	if _, err := client.Recover(t.Context(), dead, "operation"); !errors.Is(err, queue.ErrLease) {
		t.Fatalf("Recover without guard = %v", err)
	}
	in := prompt()
	in.BYOK = &BYOK{Provider: "gemini", Key: "test-key"}
	_, err := client.Complete(t.Context(), guard, in)
	checkFailure(t, err, CauseBYOK, 0, queue.Fail(CauseBYOK))
	in.BYOK = &BYOK{Provider: BYOKOpenAI, Key: " "}
	_, err = client.Complete(t.Context(), guard, in)
	checkFailure(t, err, CauseBYOK, 0, queue.Fail(CauseBYOK))
	in.BYOK, in.Step = nil, ""
	_, err = client.Complete(t.Context(), guard, in)
	checkFailure(t, err, CauseRejected, 0, queue.Fail(CauseRejected))
}

func TestRecoverLooksUpTheSameKeyWithoutPosting(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		status   int
		body     string
		expected error
		ack      string
	}{
		{"committed", http.StatusOK, okCompletion, nil, "correct"},
		{"missing ack", http.StatusOK, okCompletion, ErrNotCommitted, ""},
		{"mismatched ack", http.StatusOK, okCompletion, ErrNotCommitted, "other"},
		{"missing", http.StatusNotFound, gatewayError("", "idempotency_not_found", ""), ErrNotCommitted, ""},
		{"expired", http.StatusGone, gatewayError("", "idempotency_expired", ""), ErrNotCommitted, ""},
		{"indeterminate", http.StatusConflict, gatewayError("", "idempotency_indeterminate", ""), ErrNotCommitted, ""},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			guard := queue.GuardedForTest(t, "owner", "job")
			client := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				const key = "d2241ab4-95e3-880b-bda8-23f7e5334859"
				if r.Method != http.MethodGet || r.URL.Path != "/v1/chat/completions/operations/"+key ||
					r.Header.Get("X-Omi-User-Uid") != "owner" || r.Header.Get("Authorization") != "Bearer test-service" ||
					r.Header.Get("X-Omi-Service-Caller") != "backend" || r.Header.Get("X-Omi-Request-Id") != key {
					t.Errorf("unexpected recovery request: %s %s", r.Method, r.URL.Path)
				}
				if tc.ack != "correct" {
					w.Header().Set(idempotencyAck, tc.ack)
				}
				writeResponse(t, w, tc.status, tc.body)
			}))
			text, err := client.Recover(t.Context(), guard, "notes")
			if !errors.Is(err, tc.expected) || (tc.expected == nil && text != `{"title":"Example"}`) {
				t.Fatalf("Recover = %q, %v", text, err)
			}
		})
	}
}

func TestCompleteRejectsUnacknowledgedSuccess(t *testing.T) {
	t.Parallel()
	client := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Del(idempotencyAck)
		writeResponse(t, w, http.StatusOK, okCompletion)
	}))
	_, err := client.Complete(t.Context(), queue.GuardedForTest(t, "owner", "job"), prompt())
	checkFailure(t, err, CauseIndeterminate, http.StatusOK, queue.Fail(CauseIndeterminate))
}

func TestBYOKEnvelopeDoesNotRetryOrFallBack(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	client := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.Header.Get("X-Omi-Byok-Openai-Key") != "test-user-key" ||
			r.Header.Get("Authorization") != "Bearer test-service" ||
			r.Header.Get("X-Omi-App-Platform") != "" {
			t.Error("incorrect BYOK envelope")
		}
		writeResponse(t, w, http.StatusUnauthorized, `{"error":{"message":"sensitive","type":"authentication_error","code":"credential_failure","param":null,"failure_class":"byok_auth"}}`)
	}))
	in := prompt()
	in.BYOK = &BYOK{Provider: BYOKOpenAI, Key: "test-user-key"}
	in.AppPlatform = "unrecognized"
	_, err := client.Complete(t.Context(), queue.GuardedForTest(t, "owner", "job"), in)
	checkFailure(t, err, CauseBYOK, http.StatusUnauthorized, queue.Fail(CauseBYOK))
	if calls.Load() != 1 {
		t.Fatalf("requests = %d", calls.Load())
	}
}

func checkFailure(t *testing.T, err error, cause queue.Cause, status int, outcome queue.Outcome) {
	t.Helper()
	fault, ok := errors.AsType[*CallError](err)
	if !ok || fault.Cause != cause || fault.Status != status {
		t.Fatalf("error = %v, want gateway cause %s with status %d", err, cause, status)
	}
	if got := queue.FromError(err, "undeclared"); got != outcome {
		t.Errorf("queue outcome = %#v, want %#v", got, outcome)
	}
	if strings.Contains(err.Error(), "sensitive") {
		t.Error("remote response text leaked")
	}
}

func TestGatewayFailureEnvelopesMapToQueueOutcomes(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name   string
		status int
		body   string
		cause  queue.Cause
		retry  bool
	}{
		{"validation", 400, gatewayError("invalid_request_error", "invalid_request", ""), CauseRejected, false},
		{"capability", 400, gatewayError("invalid_request_error", "capability_not_supported", "capability_mismatch"), CauseRejected, false},
		{"service auth invalid token", 401, `{"detail":"sensitive"}`, CauseServiceAuth, true},
		{"service auth invalid caller", 403, `{"detail":"sensitive"}`, CauseServiceAuth, true},
		{"deleting owner", 403, gatewayError("", "idempotency_owner_unavailable", ""), CauseRejected, false},
		{"BYOK provider timeout", 401, gatewayError("authentication_error", "credential_failure", "timeout_before_output"), CauseTransient, true},
		{"BYOK provider down", 401, gatewayError("authentication_error", "credential_failure", "provider_5xx_omi_paid"), CauseTransient, true},
		{"long BYOK rejection", 401, paddedGatewayError(20 << 10), CauseBYOK, false},
		{"oversized error falls back to status", 401, paddedGatewayError(70 << 10), CauseServiceAuth, true},
		{"bare 404 on older replica", 404, `{"detail":"Not Found"}`, CauseTransient, true},
		{"non-JSON 404 on older replica", 404, "Not Found", CauseTransient, true},
		{"missing idempotency claim on POST", 404, gatewayError("", "idempotency_not_found", ""), CauseIndeterminate, false},
		{"model missing", 404, gatewayError("api_error", "model_not_found", ""), CauseRejected, false},
		{"bad route", 503, gatewayError("invalid_request_error", "invalid_route_config", "invalid_config"), CauseRejected, false},
		{"provider timeout", 502, gatewayError("api_error", "provider_failure", "timeout_before_output"), CauseTransient, true},
		{"proxy timeout", 504, "<html>sensitive</html>", CauseTransient, true},
		{"managed capacity", 502, gatewayError("api_error", "provider_failure", "reserved_capacity_unavailable"), CauseTransient, true},
		{"managed provider 429", 502, gatewayError("api_error", "provider_failure", "provider_429_omi_paid"), CauseQuota, true},
		{"key pending", 409, gatewayError("", "idempotency_pending", ""), CauseTransient, true},
		{"key conflict", 409, gatewayError("", "idempotency_conflict", ""), CauseRejected, false},
		{"key indeterminate", 409, gatewayError("", "idempotency_indeterminate", ""), CauseIndeterminate, false},
		{"bare 429", 429, "", CauseQuota, true},
		{"BYOK quota", 429, gatewayError("rate_limit_error", "credential_failure", "byok_quota"), CauseBYOKQuota, false},
		{"BYOK rate limit", 429, gatewayError("rate_limit_error", "credential_failure", "byok_rate_limit"), CauseBYOKRateLimit, true},
		{"missing BYOK key", 401, gatewayError("authentication_error", "credential_failure", "missing_byok_key"), CauseBYOK, false},
		{"unsupported BYOK", 401, gatewayError("authentication_error", "credential_failure", "byok_unsupported_provider"), CauseBYOK, false},
		{"refusal", 200, `{"choices":[{"finish_reason":"stop","message":{"content":null,"refusal":"sensitive"}}]}`, CauseRejected, false},
		{"content filter", 200, `{"choices":[{"finish_reason":"content_filter","message":{"content":""}}]}`, CauseRejected, false},
		{"truncated", 200, `{"choices":[{"finish_reason":"length","message":{"content":"sensitive"}}]}`, CauseRejected, false},
		{"malformed", 200, `{"choices":[`, CauseRejected, false},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			client := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.Header().Set("Retry-After", "12")
				writeResponse(t, w, tc.status, tc.body)
			}))
			_, err := client.Complete(t.Context(), queue.GuardedForTest(t, "owner", "job"), prompt())
			outcome := queue.Fail(tc.cause)
			if tc.retry {
				outcome = queue.Retry(tc.cause, 12*time.Second)
			}
			checkFailure(t, err, tc.cause, tc.status, outcome)
		})
	}
}

func paddedGatewayError(size int) string {
	return fmt.Sprintf(`{"error":{"message":%q,"code":"credential_failure","failure_class":"byok_auth"}}`,
		strings.Repeat("sensitive ", size/10))
}

func gatewayError(kind, code, failureClass string) string {
	return fmt.Sprintf(`{"error":{"message":"sensitive","type":%q,"param":null,"code":%q,"failure_class":%q}}`, kind, code, failureClass)
}

func TestTransportFailureIsTransient(t *testing.T) {
	t.Parallel()
	client := testClient(t, http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
		panic(http.ErrAbortHandler)
	}))
	_, err := client.Complete(t.Context(), queue.GuardedForTest(t, "owner", "job"), prompt())
	checkFailure(t, err, CauseTransient, 0, queue.Retry(CauseTransient, 0))
}
