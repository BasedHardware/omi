package integrations

import (
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/netip"
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
			r.URL.Query().Get("uid") != "owner+test&1" || r.Header.Get(idempotencyHeader) != "python-fanout" ||
			r.Header.Get("Content-Type") != "application/json" || r.Header.Get("X-Plugin-Signature") != "signed" ||
			string(body) != `{"transcript_segments":[]}` {
			t.Error("wire contract changed")
		}
		http.Redirect(w, r, "/redirect", http.StatusTemporaryRedirect)
	}))
	defer server.Close()
	d := integrationfanout.Delivery{
		URL: server.URL + "/created?token=a%2Bb&uid=other", Body: []byte(`{"transcript_segments":[]}`),
		IdempotencyKey: "python-fanout", Headers: map[string]string{"X-Plugin-Signature": "signed"},
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
			URL: server.URL + path, Body: []byte(`{}`), IdempotencyKey: "key",
		})
		if err != nil || got.Disposition != want {
			t.Errorf("%s: got %+v, %v, want %v", path, got, err, want)
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
