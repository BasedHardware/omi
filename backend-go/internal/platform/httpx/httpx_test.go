package httpx_test

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
)

func client(t *testing.T, handler http.HandlerFunc) *httpx.Client {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	c, err := httpx.New(server.URL, 2, 5*time.Second, clock.Fixed{T: time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c.Close)
	return c
}

// writeBody writes a fixture body. A failed write surfaces in the client as a transport
// fault, which fails the case that expected something else.
func writeBody(w http.ResponseWriter, body string) {
	if _, err := w.Write([]byte(body)); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
	}
}

func TestDoDecodesASuccessfulResponseAndSendsHeaders(t *testing.T) {
	t.Parallel()
	c := client(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Key") != "k1" || r.Header.Get("X-Empty") != "" {
			t.Errorf("headers: %v", r.Header)
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("a request with a body must declare JSON, got %q", r.Header.Get("Content-Type"))
		}
		if _, err := w.Write([]byte(`{"value":"ok"}`)); err != nil {
			t.Error(err)
		}
	})
	var out struct {
		Value string `json:"value"`
	}
	fault := c.Do(t.Context(), httpx.Request{
		Method: http.MethodPost, Path: "/x", Body: map[string]string{"a": "b"}, Out: &out,
		Header: map[string]string{"X-Key": "k1", "X-Empty": ""},
	})
	if fault != nil || out.Value != "ok" {
		t.Fatalf("got fault=%v out=%+v", fault, out)
	}
}

func TestDoClassifiesEachFailure(t *testing.T) {
	t.Parallel()
	cases := map[string]struct {
		handler http.HandlerFunc
		body    any
		want    httpx.Fault
	}{
		"status with code and retry-after": {
			handler: func(w http.ResponseWriter, _ *http.Request) {
				w.Header().Set("Retry-After", "7")
				w.WriteHeader(http.StatusTooManyRequests)
				writeBody(w, `{"error":"slow_down"}`)
			},
			want: httpx.Fault{Kind: httpx.FaultStatus, Status: 429, Code: "slow_down", RetryAfter: 7 * time.Second},
		},
		"status with an unreadable error body": {
			handler: func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusBadGateway) },
			want:    httpx.Fault{Kind: httpx.FaultStatus, Status: 502},
		},
		"200 with a body that is not the expected json": {
			handler: func(w http.ResponseWriter, _ *http.Request) {
				writeBody(w, `{"value":`)
			},
			want: httpx.Fault{Kind: httpx.FaultTransport},
		},
		"200 with the wrong json type": {
			handler: func(w http.ResponseWriter, _ *http.Request) {
				writeBody(w, `{"value":42}`)
			},
			want: httpx.Fault{Kind: httpx.FaultDecode},
		},
		"a body that cannot be encoded": {
			handler: func(http.ResponseWriter, *http.Request) {},
			body:    func() {},
			want:    httpx.Fault{Kind: httpx.FaultEncode},
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			var out struct {
				Value string `json:"value"`
			}
			fault := client(t, tc.handler).Do(t.Context(), httpx.Request{Method: http.MethodPost, Path: "/x", Body: tc.body, Out: &out})
			if fault == nil || *fault != tc.want {
				t.Fatalf("got %+v, want %+v", fault, tc.want)
			}
		})
	}
}

func TestDoReportsNoResponseAsTransport(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	c, err := httpx.New(server.URL, 1, time.Second, clock.System{})
	if err != nil {
		t.Fatal(err)
	}
	server.Close()
	fault := c.Do(t.Context(), httpx.Request{Method: http.MethodGet, Path: "/x"})
	if fault == nil || fault.Kind != httpx.FaultTransport {
		t.Fatalf("got %+v, want a transport fault", fault)
	}
}

func TestNewRejectsABaseThatIsNotAPlainOrigin(t *testing.T) {
	t.Parallel()
	for _, base := range []string{"", "ftp://host", "http://user:pass@host", "http://host?q=1", "http://host#frag", "host:80"} {
		if _, err := httpx.New(base, 1, time.Second, clock.System{}); err == nil {
			t.Errorf("%q: expected an error", base)
		}
	}
}

func TestRetryAfter(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 11, 19, 11, 0, 0, 0, time.UTC)
	for value, want := range map[string]time.Duration{
		"17": 17 * time.Second,
		now.Add(15 * time.Second).Format(http.TimeFormat):  15 * time.Second,
		now.Add(-15 * time.Second).Format(http.TimeFormat): 0,
		"garbage": 0,
		"-15":     0,
		"":        0,
	} {
		if got := httpx.RetryAfter(value, now); got != want {
			t.Errorf("%q: got %v, want %v", value, got, want)
		}
	}
}

func TestPathEscapesEachSegment(t *testing.T) {
	t.Parallel()
	if got := httpx.Path("/accounts", "a/b", "c d", ".."); got != "/accounts/a%2Fb/c%20d/.." {
		t.Fatalf("got %q", got)
	}
}
