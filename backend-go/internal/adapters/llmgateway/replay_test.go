package llmgateway

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/http/httptrace"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestReplayableRecoversAndReplaysAfterTheFirstResponseIsLost(t *testing.T) {
	t.Parallel()
	var mu sync.Mutex
	committed := map[string]string{}
	var submissions, providerCalls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		key := r.Header.Get("X-Omi-Request-Id")
		w.Header().Set(idempotencyAck, key)
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/v1/chat/completions/operations":
			if key == "" || key != r.Header.Get(idempotencyHeader) {
				t.Error("missing or inconsistent operation key")
			}
			submissions++
			if committed[key] == "" {
				providerCalls++
				committed[key] = okCompletion
				panic(http.ErrAbortHandler)
			}
		case r.Method == http.MethodGet && r.URL.Path == "/v1/chat/completions/operations/"+key:
		default:
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		writeResponse(t, w, http.StatusOK, committed[key])
	}))
	t.Cleanup(server.Close)

	request := prompt()
	first := dialTestGateway(t, server.URL, clock.System{})
	_, err := first.Complete(t.Context(), queue.GuardedForTest(t, "owner", "job"), request)
	checkFailure(t, err, CauseTransient, 0, queue.Retry(CauseTransient, 0))

	restarted := dialTestGateway(t, server.URL, clock.System{})
	guard := queue.GuardedForTest(t, "owner", "job")
	const want = `{"title":"Example"}`
	got, err := restarted.Recover(t.Context(), guard, request.Step)
	if err != nil || got != want {
		t.Fatalf("Recover = %q, %v", got, err)
	}
	got, err = restarted.Complete(t.Context(), guard, request)
	if err != nil || got != want {
		t.Fatalf("replayed Complete = %q, %v", got, err)
	}
	mu.Lock()
	defer mu.Unlock()
	if submissions != 2 || providerCalls != 1 {
		t.Fatalf("submissions = %d, provider calls = %d", submissions, providerCalls)
	}
}

func TestOlderGatewayCannotDispatchThroughTheUnkeyedRoute(t *testing.T) {
	t.Parallel()
	legacy := http.NewServeMux()
	legacy.HandleFunc("POST /v1/chat/completions", func(_ http.ResponseWriter, _ *http.Request) {
		t.Error("paid submission reached the legacy unkeyed route")
	})
	client := testClient(t, legacy)
	_, err := client.Complete(t.Context(), queue.GuardedForTest(t, "owner", "job"), prompt())
	checkFailure(t, err, CauseTransient, http.StatusNotFound, queue.Retry(CauseTransient, 0))
}

func TestCompleteFencesPaidReplayByJobCreatedAt(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, time.November, 19, 20, 0, 0, 0, time.UTC)
	skewGuard := queue.GuardedForTest(t, "owner", "skew-job")
	skewKey := requestID(skewGuard.Operation("notes"))
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Header.Get(idempotencyHeader) != skewKey {
			t.Error("invalid job age triggered a paid submission")
		}
		w.Header().Set(idempotencyAck, r.Header.Get("X-Omi-Request-Id"))
		writeResponse(t, w, http.StatusOK, okCompletion)
	}))
	t.Cleanup(server.Close)
	client := dialTestGateway(t, server.URL, clock.Fixed{T: now})
	guard := queue.GuardedForTest(t, "owner", "job")
	tests := []struct {
		name    string
		created time.Time
		cause   queue.Cause
	}{
		{"missing", time.Time{}, CauseRejected},
		{"beyond clock skew", now.Add(time.Minute + time.Nanosecond), CauseRejected},
		{"at cutoff", now.Add(-29 * 24 * time.Hour), CauseExpired},
		{"after cutoff", now.Add(-30 * 24 * time.Hour), CauseExpired},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			in := prompt()
			in.JobCreatedAt = tc.created
			_, err := client.Complete(t.Context(), guard, in)
			checkFailure(t, err, tc.cause, 0, queue.Fail(tc.cause))
		})
	}
	in := prompt()
	in.JobCreatedAt = now.Add(time.Minute)
	if got, err := client.Complete(t.Context(), skewGuard, in); err != nil || got == "" {
		t.Fatalf("Complete at accepted clock skew = %q, %v", got, err)
	}
	if got, err := client.Recover(t.Context(), guard, "notes"); err != nil || got == "" {
		t.Fatalf("read-only Recover = %q, %v", got, err)
	}
}

func TestCanceledContextAndRedirectNeverDispatch(t *testing.T) {
	t.Parallel()
	t.Run("canceled calls", func(t *testing.T) {
		t.Parallel()
		client := testClient(t, http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
			t.Error("canceled request reached gateway")
		}))
		guard := queue.GuardedForTest(t, "owner", "job")
		ctx, cancel := context.WithCancel(t.Context())
		cancel()
		if _, err := client.Complete(ctx, guard, prompt()); !errors.Is(err, context.Canceled) {
			t.Errorf("Complete = %v", err)
		}
		if _, err := client.Recover(ctx, guard, "notes"); !errors.Is(err, context.Canceled) {
			t.Errorf("Recover = %v", err)
		}
	})
	t.Run("redirect with uppercase URL scheme", func(t *testing.T) {
		t.Parallel()
		target := httptest.NewServer(http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
			t.Error("client followed a redirect")
		}))
		t.Cleanup(target.Close)
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			http.Redirect(w, r, target.URL, http.StatusFound)
		}))
		t.Cleanup(server.Close)
		client := dialTestGateway(t, "HTTP://"+strings.TrimPrefix(server.URL, "http://"), clock.System{})
		_, err := client.Complete(t.Context(), queue.GuardedForTest(t, "owner", "job"), prompt())
		checkFailure(t, err, CauseRejected, http.StatusFound, queue.Fail(CauseRejected))
	})
}

func TestBYOKControlsAndManagedOnlyLanesAreRejectedLocally(t *testing.T) {
	t.Parallel()
	client := testClient(t, http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
		t.Error("rejected BYOK request reached gateway")
	}))
	tests := []struct {
		feature Feature
		key     string
	}{
		{ConversationStructure, "test\nkey"},
		{ConversationStructure, "test-key\n"},
		{ConversationV3Summary, "test-key"},
		{StructureShadow, "test-key"},
		{ActionsShadow, "test-key"},
	}
	for _, tc := range tests {
		t.Run(string(tc.feature), func(t *testing.T) {
			t.Parallel()
			in := prompt()
			in.Feature = tc.feature
			in.Schema = &StrictSchema{Name: "TestSchema", JSON: []byte(`{"type":"object"}`)}
			if tc.feature == ConversationStructure {
				in.Schema = nil
			}
			in.BYOK = &BYOK{Provider: BYOKOpenAI, Key: tc.key}
			_, err := client.Complete(t.Context(), queue.GuardedForTest(t, "owner", "job"), in)
			checkFailure(t, err, CauseBYOK, 0, queue.Fail(CauseBYOK))
		})
	}
}

func TestStrictSchemaRequiresGatewayLaneSupport(t *testing.T) {
	t.Parallel()
	guard := queue.GuardedForTest(t, "owner", "job")
	const schema = `{"type":"object"}`
	client := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body completionRequest
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		if body.Model != "omi:auto:conversation-v3-summary" &&
			body.Model != "omi:auto:conv-app-select" && body.Model != "omi:auto:external-structure" {
			t.Errorf("unsupported lane reached gateway: %s", body.Model)
		}
		if body.ResponseFormat == nil || !body.ResponseFormat.JSONSchema.Strict {
			t.Error("schema mode was omitted")
		}
		writeResponse(t, w, http.StatusOK, okCompletion)
	}))
	for _, feature := range []Feature{ConversationStructure, ConversationDiscard, ConversationActions,
		ConversationFolder, ConversationAppResult, Memories, MemoryL1} {
		in := prompt()
		in.Feature = feature
		in.Step = string(feature)
		in.Schema = &StrictSchema{Name: "TestSchema", JSON: []byte(schema)}
		_, err := client.Complete(t.Context(), guard, in)
		checkFailure(t, err, CauseRejected, 0, queue.Fail(CauseRejected))
	}
	for _, feature := range []Feature{ConversationAppSelect, ExternalStructure, ConversationV3Summary} {
		in := prompt()
		in.Feature = feature
		in.Step = string(feature)
		in.Schema = &StrictSchema{Name: "TestSchema", JSON: []byte(schema)}
		if _, err := client.Complete(t.Context(), guard, in); err != nil {
			t.Errorf("%s: %v", feature, err)
		}
	}
}

func TestGatewayPoolReusesConnectionsAndCloseReleasesThem(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set(idempotencyAck, r.Header.Get("X-Omi-Request-Id"))
		writeResponse(t, w, http.StatusOK, okCompletion)
	}))
	t.Cleanup(server.Close)
	adapter, err := New(Config{BaseURL: server.URL, ServiceToken: "test-service", Timeout: time.Second,
		IdleConnections: 17}, clock.System{})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(adapter.Close)
	concrete, ok := adapter.(*client)
	if !ok {
		t.Fatal("unexpected adapter type")
	}
	transport, ok := concrete.http.Transport.(*http.Transport)
	if !ok || transport.MaxIdleConns != 17 || transport.MaxIdleConnsPerHost != 17 || transport.IdleConnTimeout <= 0 {
		t.Fatal("gateway transport does not have the configured idle pool")
	}
	guard := queue.GuardedForTest(t, "owner", "job")
	connections := make(chan bool, 1)
	ctx := httptrace.WithClientTrace(t.Context(), &httptrace.ClientTrace{
		GotConn: func(info httptrace.GotConnInfo) {
			connections <- info.Reused
		},
	})
	for _, wantReuse := range []bool{false, true, false} {
		if _, err := adapter.Recover(ctx, guard, "notes"); err != nil {
			t.Fatal(err)
		}
		select {
		case gotReuse := <-connections:
			if gotReuse != wantReuse {
				t.Errorf("connection reused = %t, want %t", gotReuse, wantReuse)
			}
		default:
			t.Fatal("gateway connection was not observed")
		}
		if wantReuse {
			adapter.Close()
		}
	}
}

func TestDispatchChecksTheGuardAfterRequestConstruction(t *testing.T) {
	t.Parallel()
	adapter := testClient(t, http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
		t.Error("expired guard dispatched a request")
	}))
	concrete, ok := adapter.(*client)
	if !ok {
		t.Fatal("unexpected adapter type")
	}
	ctx := context.WithoutCancel(t.Context())
	var guard queue.Guarded
	var req *http.Request
	// GuardedForTest registers its cleanup below, so it expires before this check.
	t.Cleanup(func() {
		if req == nil {
			return
		}
		if _, err := concrete.send(guard, req, req.Header.Get(idempotencyHeader), false); !errors.Is(err, queue.ErrLease) {
			t.Errorf("send = %v, want expired guard", err)
		}
	})
	guard = queue.GuardedForTest(t, "owner", "job")
	var err error
	req, err = concrete.request(ctx, guard, prompt())
	if err != nil {
		t.Fatal(err)
	}
}
