package integrations

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	appKeyHeader  = "X-Omi-Idempotency-Key"
	devKeyHeader  = "Idempotency-Key"
	responseLimit = 64 << 10
)

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

// Send makes one delivery attempt. The status acknowledges delivery even when
// the optional response body is unreadable.
func (s *Sender) Send(ctx context.Context, g queue.Guarded, d integrationfanout.Delivery) (integrationfanout.Result, error) {
	if err := g.Err(); err != nil {
		return integrationfanout.Result{}, err
	}
	developer := d.AppID == ""
	request := buildRequest(ctx, g.Tenant(), d)
	if request == nil {
		return invalidDestination(developer), nil
	}
	resp, err := s.client.Do(request)
	switch {
	case err == nil:
		result := resultForStatus(resp.StatusCode, resp.Header.Get("Retry-After"), developer, s.clock.Now())
		result.Message = readMessage(resp, !developer && result.Disposition == integrationfanout.Accepted)
		return result, nil
	case ctx.Err() != nil:
		return integrationfanout.Result{}, ctx.Err()
	case errors.Is(err, errUnsafeAddress):
		return invalidDestination(developer), nil
	default:
		return transportFailure(err), nil
	}
}

func invalidDestination(developer bool) integrationfanout.Result {
	result := integrationfanout.Result{Disposition: integrationfanout.Rejected, Failure: integrationfanout.InvalidDestination}
	if developer {
		result.Status = http.StatusBadRequest // Python's synthetic rejection for bad targets.
	}
	return result
}

func transportFailure(err error) integrationfanout.Result {
	result := integrationfanout.Result{Disposition: integrationfanout.Transient, Failure: integrationfanout.TransportFailure}
	if networkErr, ok := errors.AsType[net.Error](err); ok && networkErr.Timeout() {
		result.Failure = integrationfanout.Timeout
	}
	return result
}

func buildRequest(ctx context.Context, owner string, d integrationfanout.Delivery) *http.Request {
	u, err := url.Parse(d.URL)
	if err != nil || u.Hostname() == "" || (u.Scheme != "http" && u.Scheme != "https") ||
		u.Opaque != "" || !json.Valid(d.Body) {
		return nil
	}
	u.Fragment, u.RawFragment = "", ""
	u.RawQuery = ownerQuery(u.RawQuery, owner)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), bytes.NewReader(d.Body))
	if err != nil {
		return nil
	}
	for name, value := range d.Headers {
		req.Header.Set(name, value)
	}
	req.Header.Del(devKeyHeader)
	req.Header.Del(appKeyHeader)
	req.Header.Set("Content-Type", "application/json")
	header := appKeyHeader
	if d.AppID == "" {
		header = devKeyHeader
	}
	req.Header.Set(header, d.IdempotencyKey)
	req.GetBody = nil
	return req
}

// ownerQuery replaces uid without reordering or re-encoding unrelated query bytes.
func ownerQuery(query, owner string) string {
	var parts []string
	if query != "" {
		for part := range strings.SplitSeq(query, "&") {
			name, _, _ := strings.Cut(part, "=")
			if key, err := url.QueryUnescape(name); err != nil || key != "uid" {
				parts = append(parts, part)
			}
		}
	}
	return strings.Join(append(parts, "uid="+url.QueryEscape(owner)), "&")
}

func resultForStatus(status int, retryAfter string, developer bool, now time.Time) integrationfanout.Result {
	result := integrationfanout.Result{Disposition: integrationfanout.Accepted, Status: status}
	if status >= 200 && status < 300 {
		return result
	}
	result.Failure = integrationfanout.HTTPFailure
	result.Disposition = integrationfanout.Rejected
	if retryableStatus(status, developer) {
		result.Disposition = integrationfanout.Transient
		result.RetryAfter = httpx.RetryAfter(retryAfter, now)
	}
	return result
}

func retryableStatus(status int, developer bool) bool {
	if status >= 500 || status == http.StatusRequestTimeout || status == http.StatusTooManyRequests {
		return true
	}
	if developer {
		return status < 400 // Redirects are retried at the original URL.
	}
	return status == http.StatusTooEarly
}

func readMessage(resp *http.Response, parse bool) string {
	var data []byte
	var readErr error
	if resp.StatusCode != http.StatusSwitchingProtocols {
		data, readErr = io.ReadAll(io.LimitReader(resp.Body, responseLimit+1))
	}
	closeErr := resp.Body.Close()
	if !parse || readErr != nil || closeErr != nil || len(data) > responseLimit {
		return ""
	}
	var payload struct {
		Message string `json:"message"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return ""
	}
	return payload.Message
}
