package integrations

import (
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func testSender(t *testing.T, server *httptest.Server, timeout time.Duration) *Sender {
	t.Helper()
	s := &Sender{client: newClient(timeout, server.Client().Transport), clock: clock.System{}}
	t.Cleanup(s.Close)
	return s
}

func TestSenderPreservesWireContractAndRefusesRedirect(t *testing.T) {
	t.Parallel()
	var redirected atomic.Bool
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/redirect" {
			redirected.Store(true)
			return
		}
		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Error(err)
		}
		if r.Method != http.MethodPost || r.URL.Query().Get("token") != "a+b" ||
			r.URL.Query().Get("uid") != "owner+test&1" || r.Header.Get(appKeyHeader) != "python-fanout" ||
			r.Header.Get(devKeyHeader) != "" || r.URL.RawQuery != "z=a%20b&token=a%2Bb&z=a+b&uid=owner%2Btest%261" ||
			r.Header.Get("Content-Type") != "application/json" || r.Header.Get("X-Plugin-Signature") != "signed" ||
			string(body) != `{"transcript_segments":[]}` {
			t.Error("wire contract changed")
		}
		http.Redirect(w, r, "/redirect", http.StatusTemporaryRedirect)
	}))
	defer server.Close()
	d := integrationfanout.Delivery{
		AppID: "app", URL: server.URL + "/created?z=a%20b&token=a%2Bb&%75id=other&z=a+b#fragment", Body: []byte(`{"transcript_segments":[]}`),
		IdempotencyKey: "python-fanout", Headers: map[string]string{"X-Plugin-Signature": "signed", devKeyHeader: "ignored"},
	}
	g := queue.GuardedForTest(t, "owner+test&1", "job")
	got, err := testSender(t, server, time.Second).Send(t.Context(), g, d)
	if err != nil || got.Disposition != integrationfanout.Rejected || redirected.Load() {
		t.Fatalf("redirect result: %+v, %v; followed=%v", got, err, redirected.Load())
	}
}

func TestSenderTimesOutBeforeHeadersButAcceptsWithoutWaitingForBody(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, err := io.Copy(io.Discard, r.Body); err != nil {
			t.Error(err)
			return
		}
		if r.URL.Path == "/accepted" {
			w.WriteHeader(http.StatusAccepted)
			if err := http.NewResponseController(w).Flush(); err != nil {
				t.Error(err)
			}
		}
		<-r.Context().Done()
	}))
	defer server.Close()
	g := queue.GuardedForTest(t, "owner", "job")
	s := testSender(t, server, 250*time.Millisecond)
	for path, want := range map[string]integrationfanout.Disposition{
		"/slow": integrationfanout.Transient, "/accepted": integrationfanout.Accepted,
	} {
		got, err := s.Send(t.Context(), g, integrationfanout.Delivery{
			AppID: "app", URL: server.URL + path, Body: []byte(`{}`), IdempotencyKey: "key",
		})
		if err != nil || got.Disposition != want {
			t.Errorf("%s: got %+v, %v, want %v", path, got, err, want)
		}
		if path == "/slow" && got.Failure != integrationfanout.Timeout {
			t.Errorf("timeout cause: %v", got.Failure)
		}
	}
}

func TestSenderRefusesPrivateAddressesAndInvalidGuards(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Error("local endpoint must never be called by the public sender")
	}))
	defer server.Close()
	s, err := NewSender(time.Second, clock.System{})
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	d := integrationfanout.Delivery{URL: server.URL, Body: []byte(`{}`), IdempotencyKey: "key"}
	if _, guardErr := s.Send(t.Context(), queue.Guarded{}, d); !errors.Is(guardErr, queue.ErrLease) {
		t.Fatalf("invalid guard: %v", guardErr)
	}
	got, err := s.Send(t.Context(), queue.GuardedForTest(t, "owner", "job"), d)
	if err != nil || got.Disposition != integrationfanout.Rejected {
		t.Fatalf("private destination: %+v, %v", got, err)
	}
	ips := []netip.Addr{netip.MustParseAddr("8.8.8.8"), netip.MustParseAddr("::ffff:127.0.0.1")}
	if err := validateAddresses(ips); !errors.Is(err, errUnsafeAddress) {
		t.Fatalf("mixed public/private answers: %v", err)
	}
}

func TestDeveloperWebhookKeepsBasicAuthAndUsesDeveloperKey(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user, password, ok := r.BasicAuth()
		if !ok || user != "user" || password != "p@ss" ||
			r.Header.Get(appKeyHeader) != "" || r.Header.Get(devKeyHeader) != "developer-key" ||
			r.URL.RawQuery != "z=one+two&flag=&tag=%2F&z=+&broken=%25ZZ&encoding=%EF%BF%BD%EF%BF%BD%EF%BF%BDx&uid=owner" || r.URL.Fragment != "" {
			t.Error("developer webhook request changed")
		}
		w.WriteHeader(http.StatusTemporaryRedirect)
	}))
	defer server.Close()
	d := integrationfanout.Delivery{
		URL:  strings.Replace(server.URL, "://", "://user:p%40ss@", 1) + "?z=one%20two&flag&&%75id=old&tag=%2f&z=%20&broken=%ZZ&encoding=%FF%FF%E2%82x#discard",
		Body: []byte(`{}`), IdempotencyKey: "developer-key", Headers: map[string]string{appKeyHeader: "ignored"},
	}
	got, err := testSender(t, server, time.Second).Send(t.Context(), queue.GuardedForTest(t, "owner", "job"), d)
	if err != nil || got.Disposition != integrationfanout.Transient || got.Status != http.StatusTemporaryRedirect {
		t.Fatalf("developer redirect: %+v, %v", got, err)
	}
}

func TestSenderClassifiesReceiverStatusAndHonorsRetryAfter(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name      string
		status    int
		app       integrationfanout.Disposition
		developer integrationfanout.Disposition
	}{
		{"accepted", http.StatusAccepted, integrationfanout.Accepted, integrationfanout.Accepted},
		{"redirect", http.StatusTemporaryRedirect, integrationfanout.Rejected, integrationfanout.Transient},
		{"bad request", http.StatusBadRequest, integrationfanout.Rejected, integrationfanout.Rejected},
		{"request timeout", http.StatusRequestTimeout, integrationfanout.Transient, integrationfanout.Transient},
		{"too early", http.StatusTooEarly, integrationfanout.Transient, integrationfanout.Rejected},
		{"rate limit", http.StatusTooManyRequests, integrationfanout.Transient, integrationfanout.Transient},
		{"unavailable", http.StatusServiceUnavailable, integrationfanout.Transient, integrationfanout.Transient},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			for developer, want := range map[bool]integrationfanout.Disposition{false: tc.app, true: tc.developer} {
				got := resultForStatus(tc.status, "7", developer, time.Time{})
				var delay time.Duration
				if want == integrationfanout.Transient {
					delay = 7 * time.Second
				}
				if got.Status != tc.status || got.Disposition != want || got.RetryAfter != delay {
					t.Errorf("developer=%v: got %+v, want disposition %v and delay %v", developer, got, want, delay)
				}
			}
		})
	}

}

func TestSenderKeepsAcceptanceWhenAppMessageIsInvalidOrOversized(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body := `{"message":42}`
		if r.URL.Path == "/large" {
			body = `{"message":"` + strings.Repeat("x", responseLimit) + `"}`
		}
		if _, err := io.WriteString(w, body); err != nil {
			return // The bounded reader may close the connection before the write completes.
		}
	}))
	defer server.Close()
	g := queue.GuardedForTest(t, "owner", "job")
	s := testSender(t, server, time.Second)
	for _, path := range []string{"/invalid", "/large"} {
		got, err := s.Send(t.Context(), g, integrationfanout.Delivery{
			AppID: "app", URL: server.URL + path, Body: []byte(`{}`), IdempotencyKey: "key",
		})
		if err != nil || got.Disposition != integrationfanout.Accepted || got.Message != "" {
			t.Errorf("%s: disposition=%v message length=%d err=%v", path, got.Disposition, len(got.Message), err)
		}
	}
}
