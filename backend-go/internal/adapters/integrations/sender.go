package integrations

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/url"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const idempotencyHeader = "X-Omi-Idempotency-Key"

// Sender posts directly to public webhook endpoints under a bounded request timeout.
type Sender struct {
	client *http.Client
	clock  clock.Clock
}

// NewSender creates a sender that resolves and pins only public addresses, without
// using environment proxies or following redirects.
func NewSender(timeout time.Duration, c clock.Clock) (*Sender, error) {
	if timeout <= 0 || c == nil {
		return nil, errors.New("integration: sender requires a positive timeout and clock")
	}
	dialer := &net.Dialer{}
	resolver := &net.Resolver{}
	transport := &http.Transport{
		DialContext:       publicDial(resolver, dialer),
		ForceAttemptHTTP2: true,
		MaxIdleConns:      32,
		IdleConnTimeout:   30 * time.Second,
	}
	return &Sender{client: newClient(timeout, transport), clock: c}, nil
}

func newClient(timeout time.Duration, transport http.RoundTripper) *http.Client {
	return &http.Client{
		Transport: transport,
		Timeout:   timeout,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

// Close releases idle connections.
func (s *Sender) Close() { s.client.CloseIdleConnections() }

// Send makes one delivery attempt. The receiver's status is the acknowledgement.
func (s *Sender) Send(ctx context.Context, g queue.Guarded, d integrationfanout.Delivery) (integrationfanout.Result, error) {
	if err := g.Err(); err != nil {
		return integrationfanout.Result{}, err
	}
	request := buildRequest(ctx, g.Tenant(), d)
	if request == nil {
		return integrationfanout.Result{Disposition: integrationfanout.Rejected}, nil
	}
	resp, err := s.client.Do(request)
	switch {
	case err == nil:
		// Headers are the acknowledgement. A slow or truncated body cannot undo a 2xx.
		if closeErr := resp.Body.Close(); closeErr != nil && resp.StatusCode < 200 {
			return integrationfanout.Result{Disposition: integrationfanout.Transient}, nil
		}
		return resultForStatus(resp.StatusCode, resp.Header.Get("Retry-After"), s.clock.Now()), nil
	case ctx.Err() != nil:
		return integrationfanout.Result{}, ctx.Err()
	case errors.Is(err, errUnsafeAddress):
		return integrationfanout.Result{Disposition: integrationfanout.Rejected}, nil
	default:
		return integrationfanout.Result{Disposition: integrationfanout.Transient}, nil
	}
}

func buildRequest(ctx context.Context, owner string, d integrationfanout.Delivery) *http.Request {
	u, err := url.Parse(d.URL)
	if err != nil || u.Hostname() == "" || (u.Scheme != "http" && u.Scheme != "https") ||
		u.User != nil || u.Fragment != "" || u.Opaque != "" || !json.Valid(d.Body) {
		return nil
	}
	query, err := url.ParseQuery(u.RawQuery)
	if err != nil {
		return nil
	}
	if query.Has("uid") {
		query.Del("uid")
		u.RawQuery = query.Encode()
	}
	if u.RawQuery != "" {
		u.RawQuery += "&"
	}
	u.RawQuery += "uid=" + url.QueryEscape(owner)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), bytes.NewReader(d.Body))
	if err != nil {
		return nil
	}
	for name, value := range d.Headers {
		req.Header.Set(name, value)
	}
	req.Header.Del("Idempotency-Key")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set(idempotencyHeader, d.IdempotencyKey)
	req.GetBody = nil
	return req
}

func resultForStatus(status int, retryAfter string, now time.Time) integrationfanout.Result {
	switch {
	case status >= 200 && status < 300:
		return integrationfanout.Result{Disposition: integrationfanout.Accepted}
	case status >= 500:
		return integrationfanout.Result{
			Disposition: integrationfanout.Transient,
			RetryAfter:  httpx.RetryAfter(retryAfter, now),
		}
	default:
		return integrationfanout.Result{Disposition: integrationfanout.Rejected}
	}
}
