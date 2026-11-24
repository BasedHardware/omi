// Package llmgateway sends guarded finalization prompts to Omi's LLM gateway.
package llmgateway

import (
	"context"
	"errors"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Feature selects a finalization gateway route and its accounting attribution.
type Feature string

// Finalization features and the two structured pilot bundles.
const (
	ConversationStructure Feature = "conv_structure"
	ConversationDiscard   Feature = "conv_discard"
	ConversationActions   Feature = "conv_action_items"
	ConversationFolder    Feature = "conv_folder"
	ConversationAppSelect Feature = "conv_app_select"
	ConversationAppResult Feature = "conv_app_result"
	ExternalStructure     Feature = "external_structure"
	ConversationV3Summary Feature = "conversation_v3_summary"
	Memories              Feature = "memories"
	MemoryL1              Feature = "memory_l1"
	StructureShadow       Feature = "conversation_structure.extract.shadow"
	ActionsShadow         Feature = "conversation_action_items.extract.shadow"
)

// ConversationApps is the Python accounting feature shared by app selection and generation.
const ConversationApps Feature = "conv_apps"

// Message is a text prompt message with its OpenAI role, such as system or user.
type Message struct {
	Role string
	Text string
}

// StrictSchema carries a JSON schema already normalized for the gateway.
type StrictSchema struct {
	Name string
	JSON []byte
}

// BYOKProvider is a provider whose key can be forwarded by this adapter.
// The selected gateway lane must accept that provider's key.
type BYOKProvider string

// Forwardable key providers. Gemini developer keys cannot be used by the Vertex adapter.
const (
	BYOKOpenAI     BYOKProvider = "openai"
	BYOKOpenRouter BYOKProvider = "openrouter"
	BYOKAnthropic  BYOKProvider = "anthropic"
)

// BYOK is the credential for this invocation. A nil credential selects managed billing.
type BYOK struct {
	Provider BYOKProvider
	Key      string
}

// Request holds data for one non-streaming completion. Step must identify one paid
// call within the job, including when the same feature is used more than once.
type Request struct {
	Step string
	// JobCreatedAt is the durable Job.CreatedAt, shared by retries and redrives.
	JobCreatedAt time.Time
	Feature      Feature
	Messages     []Message
	Schema       *StrictSchema
	UsageFeature Feature
	AppPlatform  string
	BYOK         *BYOK
}

// Config is supplied by the binary. ServiceToken is the resolved Omi gateway bearer token.
type Config struct {
	BaseURL      string
	ServiceToken string
	Timeout      time.Duration
	// IdleConnections sizes the pool to the worker count. Zero uses eight.
	IdleConnections int
}

// Replayable couples paid submission with recovery. A paid family port must require
// both operations and supply a job's durable creation time for every submission.
type Replayable interface {
	Complete(ctx context.Context, g queue.Guarded, in Request) (string, error)
	Recover(ctx context.Context, g queue.Guarded, step string) (string, error)
	// Close releases idle connections at shutdown.
	Close()
}

const (
	paidReplayHorizon      = 29 * 24 * time.Hour
	creationClockSkew      = time.Minute
	defaultIdleConnections = 8
)

type client struct {
	endpoint string
	token    string
	http     *http.Client
	clock    clock.Clock
}

// New builds a client with a bounded call timeout and redirects disabled.
func New(cfg Config, c clock.Clock) (Replayable, error) {
	base, err := url.Parse(cfg.BaseURL)
	if err != nil || base.Hostname() == "" || (base.Scheme != "http" && base.Scheme != "https") ||
		base.User != nil || base.RawQuery != "" || base.ForceQuery || base.Fragment != "" {
		return nil, errors.New("llmgateway: invalid base URL")
	}
	token := strings.TrimSpace(cfg.ServiceToken)
	if token == "" || cfg.Timeout <= 0 || c == nil {
		return nil, errors.New("llmgateway: service token, positive timeout and clock are required")
	}
	idle := cfg.IdleConnections
	if idle < 0 {
		return nil, errors.New("llmgateway: idle connections cannot be negative")
	}
	if idle == 0 {
		idle = defaultIdleConnections
	}
	return &client{
		endpoint: strings.TrimRight(base.String(), "/") + "/v1/chat/completions/operations",
		token:    token,
		clock:    c,
		http: &http.Client{
			Timeout: cfg.Timeout,
			Transport: &http.Transport{
				Proxy:                 http.ProxyFromEnvironment,
				DialContext:           (&net.Dialer{Timeout: 30 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
				ForceAttemptHTTP2:     true,
				MaxIdleConns:          idle,
				MaxIdleConnsPerHost:   idle,
				IdleConnTimeout:       90 * time.Second,
				TLSHandshakeTimeout:   10 * time.Second,
				ExpectContinueTimeout: time.Second,
			},
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}, nil
}

// Close releases the client's idle connections.
func (c *client) Close() { c.http.CloseIdleConnections() }

// Complete executes a single gateway POST and returns the first choice's text in memory.
// The operation key identifies the same gateway result across retries and takeovers.
func (c *client) Complete(ctx context.Context, g queue.Guarded, in Request) (string, error) {
	if err := g.Err(); err != nil {
		return "", err
	}
	if err := ctx.Err(); err != nil {
		return "", err
	}
	now := c.clock.Now()
	if in.JobCreatedAt.IsZero() || in.JobCreatedAt.After(now.Add(creationClockSkew)) {
		return "", classify(CauseRejected, 0, 0)
	}
	remaining := in.JobCreatedAt.Add(paidReplayHorizon).Sub(now)
	if remaining <= 0 {
		return "", classify(CauseExpired, 0, 0)
	}
	callCtx, cancel := context.WithTimeout(ctx, remaining)
	defer cancel()
	req, err := c.request(callCtx, g, in)
	if err != nil {
		return "", err
	}
	text, err := c.send(g, req, req.Header.Get(idempotencyHeader), false)
	if guardErr := g.Err(); guardErr != nil {
		return "", guardErr
	}
	if ctxErr := ctx.Err(); ctxErr != nil {
		return "", ctxErr
	}
	return text, err
}

// ErrNotCommitted means the gateway has no recoverable completion for this operation.
var ErrNotCommitted = errors.New("llmgateway: no recoverable completion")

// Recover fetches the committed result for the same guarded job and step.
// A lookup never submits work to a provider.
func (c *client) Recover(ctx context.Context, g queue.Guarded, step string) (string, error) {
	if err := g.Err(); err != nil {
		return "", err
	}
	if err := ctx.Err(); err != nil {
		return "", err
	}
	if strings.TrimSpace(step) == "" {
		return "", classify(CauseRejected, 0, 0)
	}
	key := OperationID(g, step)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.endpoint+"/"+key, nil)
	if err != nil {
		return "", classify(CauseRejected, 0, 0)
	}
	c.authorize(req, g.Tenant())
	req.Header.Set("X-Omi-Request-Id", key)
	text, err := c.send(g, req, key, true)
	if guardErr := g.Err(); guardErr != nil {
		return "", guardErr
	}
	if ctxErr := ctx.Err(); ctxErr != nil {
		return "", ctxErr
	}
	return text, err
}
