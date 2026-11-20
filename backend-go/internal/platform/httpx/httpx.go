// Package httpx is a JSON-over-HTTP client whose failures are typed.
//
// It classifies how a call failed (no response, a non-200 status, a body that could not be
// encoded or decoded). It does not decide what the failure means: whether a 409 is a retry, a
// yield or a fence belongs to the adapter that knows the remote contract.
package httpx

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
)

// FaultKind says at which point a call failed. The set is closed.
type FaultKind uint8

// The fault kinds.
const (
	// FaultEncode means the request could not be built. Retrying cannot help.
	FaultEncode FaultKind = iota + 1
	// FaultTransport means no complete response arrived. The remote may have acted.
	FaultTransport
	// FaultStatus means the remote answered with a status other than 200.
	FaultStatus
	// FaultDecode means the remote answered 200 with a body that is not the expected JSON.
	FaultDecode
)

// Fault describes a failed call. It carries no response text, so it is safe to log.
type Fault struct {
	Kind FaultKind
	// Status is the HTTP status for FaultStatus, otherwise zero.
	Status int
	// Code is the remote's machine-readable error code for FaultStatus, if it sent one.
	Code string
	// RetryAfter is the delay the remote asked for, or zero.
	RetryAfter time.Duration
}

// String names the fault without any remote text.
//
// Fault is deliberately not an error: Do returns *Fault, and a nil *Fault stored in an error
// interface would not compare equal to nil. An adapter turns a Fault into its own typed error.
func (f *Fault) String() string {
	switch f.Kind {
	case FaultEncode:
		return "request could not be encoded"
	case FaultTransport:
		return "no response"
	case FaultStatus:
		return "status " + strconv.Itoa(f.Status)
	case FaultDecode:
		return "response could not be decoded"
	}
	return "fault"
}

// Request is one call. Header values are sent as given and never logged.
type Request struct {
	Method string
	Path   string
	Body   any
	Out    any
	Header map[string]string
}

const (
	errorBodyLimit = 4 << 10
	bodyLimit      = 64 << 20
)

// Client calls one base URL.
type Client struct {
	base  string
	http  *http.Client
	clock clock.Clock
}

// New returns a client for base, which must be an http or https origin with no credentials,
// query or fragment. idle bounds the idle connection pool.
func New(base string, idle int, timeout time.Duration, c clock.Clock) (*Client, error) {
	u, err := url.Parse(base)
	if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") ||
		u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("httpx: base must be an http(s) origin without credentials, query or fragment")
	}
	transport := &http.Transport{
		MaxIdleConns:        idle,
		MaxIdleConnsPerHost: idle,
		IdleConnTimeout:     90 * time.Second,
		ForceAttemptHTTP2:   true,
	}
	return &Client{
		base: strings.TrimRight(base, "/"),
		http: &http.Client{
			Transport:     transport,
			Timeout:       timeout,
			CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		},
		clock: c,
	}, nil
}

// Close releases idle connections.
func (c *Client) Close() { c.http.CloseIdleConnections() }

// Do performs one call. It never retries: replay is the caller's decision, under its own
// attempt budget and idempotency rules.
func (c *Client) Do(ctx context.Context, in Request) *Fault {
	req, fault := c.build(ctx, in)
	if fault != nil {
		return fault
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return &Fault{Kind: FaultTransport}
	}
	fault = c.read(resp, in.Out)
	if err := resp.Body.Close(); err != nil && fault == nil {
		// The body was read; failing to close it means the connection is not reusable.
		return &Fault{Kind: FaultTransport}
	}
	return fault
}

func (c *Client) build(ctx context.Context, in Request) (*http.Request, *Fault) {
	var data []byte
	if in.Body != nil {
		var err error
		if data, err = json.Marshal(in.Body); err != nil {
			return nil, &Fault{Kind: FaultEncode}
		}
	}
	req, err := http.NewRequestWithContext(ctx, in.Method, c.base+in.Path, bytes.NewReader(data))
	if err != nil {
		return nil, &Fault{Kind: FaultEncode}
	}
	if in.Body != nil {
		req.Header.Set("Content-Type", "application/json")
		// The transport must not replay a body on its own.
		req.GetBody = nil
	}
	for name, value := range in.Header {
		if value != "" {
			req.Header.Set(name, value)
		}
	}
	return req, nil
}

func (c *Client) read(resp *http.Response, out any) *Fault {
	if resp.StatusCode != http.StatusOK {
		var payload struct {
			Error string `json:"error"`
		}
		// A missing or malformed error body leaves Code empty; the status still classifies.
		if err := json.NewDecoder(io.LimitReader(resp.Body, errorBodyLimit)).Decode(&payload); err != nil {
			payload.Error = ""
		}
		return &Fault{
			Kind:       FaultStatus,
			Status:     resp.StatusCode,
			Code:       payload.Error,
			RetryAfter: RetryAfter(resp.Header.Get("Retry-After"), c.clock.Now()),
		}
	}
	if out == nil {
		return drain(resp.Body)
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, bodyLimit)).Decode(out); err != nil {
		if _, ok := errors.AsType[*json.SyntaxError](err); ok {
			return &Fault{Kind: FaultDecode}
		}
		if _, ok := errors.AsType[*json.UnmarshalTypeError](err); ok {
			return &Fault{Kind: FaultDecode}
		}
		return &Fault{Kind: FaultTransport}
	}
	return drain(resp.Body)
}

// drain reads a little of the remaining body so the connection can be reused.
func drain(body io.Reader) *Fault {
	if _, err := io.Copy(io.Discard, io.LimitReader(body, errorBodyLimit)); err != nil {
		return &Fault{Kind: FaultTransport}
	}
	return nil
}

// RetryAfter parses a Retry-After header as delta seconds or an HTTP date, relative to now.
// An absent, malformed or past value is zero.
func RetryAfter(value string, now time.Time) time.Duration {
	if seconds, err := strconv.ParseInt(value, 10, 64); err == nil && seconds >= 0 {
		const maxSeconds = int64((1<<63 - 1) / time.Second)
		return time.Duration(min(seconds, maxSeconds)) * time.Second
	}
	if at, err := http.ParseTime(value); err == nil {
		return max(0, at.Sub(now))
	}
	return 0
}

// Path appends percent-escaped segments to prefix.
func Path(prefix string, segments ...string) string {
	var b strings.Builder
	b.WriteString(prefix)
	for _, s := range segments {
		b.WriteByte('/')
		b.WriteString(url.PathEscape(s))
	}
	return b.String()
}
