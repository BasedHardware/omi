package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"slices"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/finalizationdocs"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/integrations"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/llmgateway"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/syncfinalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func TestOrdinarySyncReplay(t *testing.T) {
	if os.Getenv("OMI_ORDINARY_SYNC_REPLAY") != "1" {
		t.Skip("invoked by the offline ordinary-sync replay driver")
	}
	var input ordinaryReplayInput
	if err := json.NewDecoder(os.Stdin).Decode(&input); err != nil {
		t.Fatal("invalid ordinary-sync replay input")
	}
	emulator := os.Getenv("FIRESTORE_EMULATOR_HOST")
	origin, ok := replayLocalDependencies(input, emulator, os.Getenv("TEST_DATABASE_URL"))
	if !ok {
		t.Fatal("ordinary-sync replay requires synthetic input, an isolated emulator project, and loopback endpoints")
	}
	// The opt-in test runs alone in one process. Disable ambient proxies and
	// Postgres service configuration before any client can resolve a connection.
	t.Setenv("NO_PROXY", "*")
	t.Setenv("no_proxy", "*")
	for _, entry := range os.Environ() {
		key, _, _ := strings.Cut(entry, "=")
		if strings.HasPrefix(key, "PG") || strings.HasSuffix(strings.ToUpper(key), "_PROXY") &&
			!strings.EqualFold(key, "NO_PROXY") {
			t.Setenv(key, "")
		}
	}
	clk := clock.System{}
	docs, err := docstore.Open(t.Context(), docstore.Config{Project: input.Project, Emulator: emulator})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if closeErr := docs.Close(); closeErr != nil {
			t.Error("could not close replay emulator client")
		}
	})
	policy := queuetest.Policy()
	policy.Workers, policy.MaxAttempts, policy.DeterministicMax = 1, 1, 1
	harness := queuetest.Open(t, policy, workerdKinds()...)
	runtime := finalizationRuntime{docs: docs, family: &finalization.Service{Queue: harness.Store}}
	if bindErr := runtime.bindFinalizationGateway(llmgateway.Config{
		BaseURL: input.Origin, ServiceToken: "replay-only", Timeout: 20 * time.Second,
	}, clk); bindErr != nil {
		t.Fatal(bindErr)
	}
	t.Cleanup(runtime.gateway.Close)
	transport, err := httpx.New(input.Origin, 2, 30*time.Second, clk)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(transport.Close)
	wireFinalizationDocuments(runtime.family, finalizationdocs.Store{
		Docs: docs, Codec: crypt.New(input.Key), Clock: clk, SyncOnly: true,
	}, nil, true)
	wireSyncFinalizationReference(runtime.family, syncfinalization.Reference{
		Client: transport, Bearer: func(context.Context) (string, error) { return "replay-only", nil },
	})
	runtime.family.Integrations = integrationDelivery{service: integrationfanout.Service{
		Sender: replayRecipient(origin, transport), Receipts: integrations.Receipts{Store: docs},
	}}

	ref := finalization.Ref{Owner: input.Owner, ID: input.Conversation}
	intent := finalization.Intent{Ref: ref, JobID: finalization.JobID(ref, 1), Revision: 1, Trigger: rules.SyncUpdate}
	if _, err := runtime.family.Dispatch(t.Context(), intent); err != nil {
		t.Fatal(err)
	}
	if input.CheckStatus {
		reportReplayStatus(t, runtime.family, intent, "QUEUED")
	}
	handlers := workerdHandlers(runtime.family)
	if handlers[finalization.Kind] != runtime.family {
		t.Fatal("ordinary finalization handler is unavailable")
	}
	harness.Start(handlers)
	job := harness.Settled(intent.JobID)
	if job.Outcome == nil || !slices.Contains(queue.Terminals(), *job.Outcome) {
		t.Fatal("ordinary finalization returned an invalid terminal status")
	}
	if input.CheckStatus {
		reportReplayStatus(t, runtime.family, intent, "TERMINAL")
	}
	fmt.Printf("ORDINARY_SYNC_RESULT=%s\nORDINARY_SYNC_CAUSE=%s\n", *job.Outcome, replayCause(job.Reason))
}

type ordinaryReplayInput struct {
	Project      string `json:"Project"`
	Origin       string `json:"Origin"`
	Key          string `json:"Key"`
	Owner        string `json:"Owner"`
	Conversation string `json:"Conversation"`
	CheckStatus  bool   `json:"CheckStatus"`
}

func replayLocalDependencies(input ordinaryReplayInput, emulator, databaseURL string) (*url.URL, bool) {
	database, dbErr := url.Parse(databaseURL)
	origin, originErr := url.Parse(input.Origin)
	if !strings.HasPrefix(input.Project, "demo-sync-replay-") || len(input.Project) <= len("demo-sync-replay-") ||
		!replayDocumentID(input.Project) || !replayDocumentID(input.Owner) || !replayDocumentID(input.Conversation) ||
		crypt.Check(input.Key) != nil || !loopbackReplayEndpoint(emulator) ||
		dbErr != nil || database.Scheme != "postgres" || !loopbackReplayEndpoint(database.Host) ||
		database.RawQuery != "sslmode=disable" || database.Fragment != "" ||
		originErr != nil || origin.Scheme != "http" || !loopbackReplayEndpoint(origin.Host) ||
		origin.User != nil || origin.Path != "" || origin.RawQuery != "" || origin.ForceQuery || origin.Fragment != "" {
		return nil, false
	}
	return origin, true
}

func replayDocumentID(id string) bool {
	return id != "" && id != "." && id != ".." && len(id) <= 128 && !strings.ContainsAny(id, "/\r\n")
}

func replayCause(reason *queue.Cause) queue.Cause {
	if reason == nil {
		return queue.CauseNone
	}
	for _, kind := range workerdKinds() {
		if slices.Contains(kind.Causes, *reason) {
			return *reason
		}
	}
	switch *reason {
	case queue.CauseNone, queue.CauseLeaseExpired, queue.CauseHandlerPanic, queue.CauseReconcileExhausted, queue.CauseUnknown:
		return *reason
	default:
		return queue.CauseUnknown
	}
}

func loopbackReplayEndpoint(address string) bool {
	host, port, err := net.SplitHostPort(address)
	number, portErr := strconv.ParseUint(port, 10, 16)
	return err == nil && host == "127.0.0.1" && portErr == nil && number > 0
}

func replayRecipient(origin *url.URL, client *httpx.Client) guardedRecipient {
	return func(ctx context.Context, g queue.Guarded, delivery integrationfanout.Delivery) (integrationfanout.Result, error) {
		if err := g.Err(); err != nil {
			return integrationfanout.Result{}, err
		}
		target, err := url.Parse(delivery.URL)
		if err != nil {
			return integrationfanout.Result{}, finalization.ErrInvalid
		}
		if target.Scheme != origin.Scheme || target.Host != origin.Host ||
			target.User != nil || !strings.HasPrefix(target.Path, "/receive/") {
			return integrationfanout.Result{Disposition: integrationfanout.Rejected}, nil
		}
		fault := client.Do(ctx, httpx.Request{
			Method: http.MethodPost, Path: target.RequestURI(), Body: json.RawMessage(delivery.Body),
			Header: map[string]string{"Idempotency-Key": delivery.IdempotencyKey},
		})
		if fault != nil && fault.Status >= 500 {
			return integrationfanout.Result{Disposition: integrationfanout.Transient}, nil
		}
		if fault != nil {
			return integrationfanout.Result{Disposition: integrationfanout.Rejected}, nil
		}
		return integrationfanout.Result{Disposition: integrationfanout.Accepted}, nil
	}
}

func TestOrdinaryReplayRejectsNonlocalDependencies(t *testing.T) {
	t.Parallel()
	const emulator = "127.0.0.1:8080"
	const database = "postgres://fixture@127.0.0.1:5432/postgres?sslmode=disable"
	input := ordinaryReplayInput{
		Project: "demo-sync-replay-fixture", Origin: "http://127.0.0.1:8001",
		Key: strings.Repeat("x", crypt.MinSecretBytes), Owner: "fixture-owner", Conversation: "fixture-conversation",
	}
	if _, ok := replayLocalDependencies(input, emulator, database); !ok {
		t.Fatal("local fixture refused")
	}
	for _, tc := range []struct {
		name, emulator, database, origin string
	}{
		{"remote emulator", "remote.invalid:8080", database, input.Origin},
		{"remote database", emulator, "postgres://fixture@remote.invalid:5432/postgres?sslmode=disable", input.Origin},
		{"database fallback", emulator, database + "&host=remote.invalid", input.Origin},
		{"remote provider", emulator, database, "http://remote.invalid:8001"},
		{"provider port zero", emulator, database, "http://127.0.0.1:0"},
		{"provider credentials", emulator, database, "http://fixture@127.0.0.1:8001"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			copyInput := input
			copyInput.Origin = tc.origin
			if _, ok := replayLocalDependencies(copyInput, tc.emulator, tc.database); ok {
				t.Fatal("invalid replay dependency accepted")
			}
		})
	}
}

func TestOrdinaryReplaySanitizesCause(t *testing.T) {
	t.Parallel()
	invalid := queue.Cause("synthetic secret\n")
	valid := finalization.CauseChanged
	if replayCause(&invalid) != queue.CauseUnknown || replayCause(&valid) != valid || replayCause(nil) != queue.CauseNone {
		t.Fatal("replay cause must come from the queue or handler registry")
	}
}
