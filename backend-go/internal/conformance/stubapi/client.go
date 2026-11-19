// Package stubapi is the adapter for the conformance kit's stub server, which plays the
// document store, the vendors, the account service and the app webhooks.
//
// CLEANUP-NOTE: this package exists so the conformance kit can drive the queue end to end.
// Each method is replaced by a real Omi adapter (Firestore, the LLM gateway, the speech
// service, app integrations) as those land. Keep the conditional-write and idempotency
// guarantees when replacing one. It is not a style reference.
package stubapi

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Vendor names a remote role of the stub. The set is closed.
type Vendor string

// The stub's roles.
const (
	AccountVendor  Vendor = "account"
	DocumentVendor Vendor = "document"
	LLMVendor      Vendor = "llm"
	SpeechVendor   Vendor = "speech"
	MemoryVendor   Vendor = "memory"
	VectorVendor   Vendor = "vector"
	AppVendor      Vendor = "app"
)

// Vendors lists every role.
func Vendors() []Vendor {
	return []Vendor{AccountVendor, DocumentVendor, LLMVendor, SpeechVendor, MemoryVendor, VectorVendor, AppVendor}
}

// Result classifies a call for metrics and for the queue. The set is closed.
type Result string

// The call results.
const (
	Succeeded     Result = "success"
	Transient     Result = "transient"
	Deterministic Result = "deterministic"
	Yielded       Result = "yield"
	Fenced        Result = "fenced"
	Dropped       Result = "dropped"
)

// Results lists every result.
func Results() []Result {
	return []Result{Succeeded, Transient, Deterministic, Yielded, Fenced, Dropped}
}

// Feature names a paid or deduplicated operation. The set is closed.
type Feature string

// The deduplicated features.
const (
	Admission   Feature = "admission"
	Notes       Feature = "notes"
	Memories    Feature = "memories"
	Speech      Feature = "speech"
	Integration Feature = "integration"
)

// Features lists every feature.
func Features() []Feature { return []Feature{Admission, Notes, Memories, Speech, Integration} }

// The causes this adapter produces. They are registered with the queue through Causes.
const (
	CauseTransport             queue.Cause = "transport"
	CauseRateLimited           queue.Cause = "rate_limited"
	CauseVendorUnavailable     queue.Cause = "vendor_unavailable"
	CauseVendorRejected        queue.Cause = "vendor_rejected"
	CauseVersionConflict       queue.Cause = "version_conflict"
	CauseRecordOwnerContention queue.Cause = "record_owner_contention"
	CauseEpisodeNotesPending   queue.Cause = "episode_notes_pending"
	CauseAccountDeleting       queue.Cause = "account_deleting"
	CauseConversationFenced    queue.Cause = "conversation_fenced"
	CauseIntegrationDropped    queue.Cause = "integration_dropped"
)

// Causes lists every cause this adapter can return.
func Causes() []queue.Cause {
	return []queue.Cause{
		CauseTransport, CauseRateLimited, CauseVendorUnavailable, CauseVendorRejected, CauseVersionConflict,
		CauseRecordOwnerContention, CauseEpisodeNotesPending, CauseAccountDeleting, CauseConversationFenced,
		CauseIntegrationDropped,
	}
}

// Observer receives call results for metrics.
type Observer interface {
	// Vendor records one call's result.
	Vendor(Vendor, Result)
	// Dedupe records whether a deduplicated feature reused stored output.
	Dedupe(Feature, bool)
}

// Fault is a failed call, already classified against the stub's contract.
type Fault struct {
	Result Result
	Cause  queue.Cause
	Delay  time.Duration
	Status int
	// HoldTenant makes a yield keep the whole tenant off the schedule for Delay.
	HoldTenant bool
}

func (f *Fault) Error() string { return string(f.Cause) }

// Outcome is what the queue should do about the fault.
func (f *Fault) Outcome() queue.Outcome {
	switch f.Result {
	case Transient:
		return queue.Retry(f.Cause, f.Delay)
	case Yielded:
		if f.HoldTenant {
			return queue.Hold(f.Cause, f.Delay)
		}
		return queue.Yield(f.Cause, f.Delay)
	case Fenced:
		return queue.Fence(f.Cause)
	case Succeeded, Deterministic, Dropped:
		return queue.Fail(f.Cause)
	}
	return queue.Fail(f.Cause)
}

// Outcome maps any error from a guarded call to a queue outcome.
func Outcome(err error) queue.Outcome {
	if errors.Is(err, queue.ErrLease) || errors.Is(err, context.Canceled) {
		return queue.Abort()
	}
	if fault, ok := errors.AsType[*Fault](err); ok {
		return fault.Outcome()
	}
	return queue.Retry(CauseTransport, 0)
}

const callTimeout = 65 * time.Second

// Client calls the stub.
type Client struct {
	http *httpx.Client
	ob   Observer
}

// New returns a client for the stub at base.
func New(base string, workers int, ob Observer, c clock.Clock) (*Client, error) {
	h, err := httpx.New(base, max(8, workers+4), callTimeout, c)
	if err != nil {
		return nil, fmt.Errorf("stub client: %w", err)
	}
	return &Client{http: h, ob: ob}, nil
}

// Close releases idle connections.
func (c *Client) Close() { c.http.Close() }

// Dedupe records a dedupe hit or miss.
func (c *Client) Dedupe(feature Feature, hit bool) { c.ob.Dedupe(feature, hit) }

type spec struct {
	vendor Vendor
	method string
	path   string
	body   any
	out    any
	// key is a caller's own vendor key, sent as a header and never stored.
	key string
	// idempotency is the stable key a receiving app uses to drop replays.
	idempotency string
	// dropTransient turns a transient failure into a recorded drop (final webhook attempt).
	dropTransient bool
}

func (c *Client) do(ctx context.Context, in spec) *Fault {
	fault := classify(in.vendor, c.http.Do(ctx, httpx.Request{
		Method: in.method, Path: in.path, Body: in.body, Out: in.out,
		Header: map[string]string{"X-Omi-Vendor-Key": in.key, "X-Omi-Idempotency-Key": in.idempotency},
	}))
	result := Succeeded
	if fault != nil {
		if in.dropTransient && fault.Result == Transient {
			fault.Result, fault.Cause = Dropped, CauseIntegrationDropped
		}
		result = fault.Result
	}
	c.ob.Vendor(in.vendor, result)
	return fault
}

// call is the common case: no idempotency key and no drop-on-final behaviour.
func (c *Client) call(ctx context.Context, v Vendor, method, path string, body, out any, key string) *Fault {
	return c.do(ctx, spec{vendor: v, method: method, path: path, body: body, out: out, key: key})
}

// classify applies the stub's contract to a typed HTTP fault.
func classify(v Vendor, f *httpx.Fault) *Fault {
	if f == nil {
		return nil
	}
	switch f.Kind {
	case httpx.FaultTransport:
		return &Fault{Result: Transient, Cause: CauseTransport}
	case httpx.FaultEncode, httpx.FaultDecode:
		return &Fault{Result: Deterministic, Cause: CauseVendorRejected}
	case httpx.FaultStatus:
		result, cause := classifyStatus(v, f.Status, f.Code)
		return &Fault{Result: result, Cause: cause, Delay: f.RetryAfter, Status: f.Status}
	}
	return &Fault{Result: Deterministic, Cause: CauseVendorRejected}
}

func classifyStatus(v Vendor, status int, code string) (Result, queue.Cause) {
	if status == http.StatusConflict {
		if result, cause, ok := classifyConflict(code); ok {
			return result, cause
		}
	}
	gone := status == http.StatusGone || status == http.StatusNotFound
	switch {
	case gone && v == DocumentVendor:
		return Fenced, CauseConversationFenced
	case v == AppVendor && status >= 400 && status < 500:
		return Dropped, CauseIntegrationDropped
	case status == http.StatusConflict && code == "version_conflict":
		return Deterministic, CauseVersionConflict
	case status == http.StatusTooManyRequests:
		return Transient, CauseRateLimited
	case status == http.StatusRequestTimeout:
		return Transient, CauseTransport
	case status >= http.StatusInternalServerError:
		return Transient, CauseVendorUnavailable
	default:
		return Deterministic, CauseVendorRejected
	}
}

// classifyConflict handles the typed 409 codes that take precedence over a role's default.
func classifyConflict(code string) (Result, queue.Cause, bool) {
	switch code {
	case "fenced":
		return Fenced, CauseConversationFenced, true
	case "record_owner_contention":
		return Yielded, CauseRecordOwnerContention, true
	case "episode_notes_pending":
		return Yielded, CauseEpisodeNotesPending, true
	case "account_deleting":
		return Yielded, CauseAccountDeleting, true
	}
	return "", "", false
}

// Digest is the lowercase hex SHA-256 of value.
func Digest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

// ID derives a stable identifier from parts, length-prefixing each so that different
// splits of the same text can never collide.
func ID(namespace string, parts ...string) string {
	var b strings.Builder
	b.WriteString(namespace)
	for _, p := range parts {
		fmt.Fprintf(&b, "%d:%s", len(p), p)
	}
	return Digest(b.String())
}

// Account is the account service's answer for one user.
type Account struct {
	Deleting bool     `json:"deleting"`
	OwnKey   bool     `json:"own_key"`
	MinWords int      `json:"min_words"`
	Apps     []string `json:"apps"`
}

// Account reads a user's account state.
func (c *Client) Account(ctx context.Context, uid string) (Account, *Fault) {
	var a Account
	f := c.do(ctx, spec{vendor: AccountVendor, method: http.MethodGet, path: httpx.Path("/accounts", uid), out: &a})
	return a, f
}

// Erase removes a user's data from the stub.
func (c *Client) Erase(ctx context.Context, uid string) *Fault {
	return c.do(ctx, spec{vendor: AccountVendor, method: http.MethodDelete, path: httpx.Path("/accounts", uid, "data")})
}

// ImplementationVersion is part of every vendor input hash: changing how input is built
// must change the hash, so stored output is not reused for different input.
const ImplementationVersion = "jobd-go-v1"

// VendorInput is the body of a paid vendor call.
type VendorInput struct {
	UID     string `json:"uid"`
	Subject string `json:"subject_id"`
	Job     string `json:"job_id"`
	Request string `json:"request_id"`
	Input   string `json:"input"`
	Hash    string `json:"input_hash"`
	Version string `json:"implementation_version"`
}

// Input builds the vendor input for a step. The request id is stable per job, step and
// input, so a repeated call is recognised by the vendor and charged once.
func Input(job queue.Job, step, input string) VendorInput {
	hash := Digest(ImplementationVersion + "\x00" + input)
	return VendorInput{
		UID: job.Tenant, Subject: job.Subject, Job: job.Key,
		Request: ID("request", job.Tenant, job.Key, step, hash),
		Input:   input, Hash: hash, Version: ImplementationVersion,
	}
}

// Guarder is the part of a claim that runs guarded calls: a queue.Run or a queue.Reconcile.
type Guarder interface {
	Guard(ctx context.Context, fn func(context.Context, queue.Guarded) error) error
}

// Guard runs a remote call under the queue's guard and keeps its typed fault.
func Guard(ctx context.Context, r Guarder, fn func(context.Context) *Fault) error {
	return r.Guard(ctx, func(ctx context.Context, _ queue.Guarded) error {
		if f := fn(ctx); f != nil {
			return f
		}
		return nil
	})
}

// Resolution maps any error from a reconciliation step to a queue resolution. The original
// terminal intent is kept until the external document is updated, fenced or found complete.
func Resolution(err error) queue.Resolution {
	if errors.Is(err, queue.ErrLease) || errors.Is(err, context.Canceled) {
		return queue.Dropped()
	}
	fault, ok := errors.AsType[*Fault](err)
	if !ok {
		return queue.Later(CauseTransport, 0)
	}
	if fault.Result == Fenced {
		return queue.Fenced(fault.Cause)
	}
	return queue.Later(fault.Cause, fault.Delay)
}
