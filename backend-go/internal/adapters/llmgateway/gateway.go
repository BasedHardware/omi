// Package llmgateway sends guarded finalization prompts to Omi's LLM gateway.
package llmgateway

import (
	"context"
	"errors"
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
	Step         string
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
}

// Client speaks the gateway's internal OpenAI-compatible API.
type Client struct {
	endpoint string
	token    string
	http     *http.Client
	clock    clock.Clock
}

// New builds a client with a bounded call timeout and redirects disabled.
func New(cfg Config, c clock.Clock) (*Client, error) {
	base, err := url.Parse(cfg.BaseURL)
	if err != nil || base.Hostname() == "" || (base.Scheme != "http" && base.Scheme != "https") ||
		base.User != nil || base.RawQuery != "" || base.ForceQuery || base.Fragment != "" {
		return nil, errors.New("llmgateway: invalid base URL")
	}
	token := strings.TrimSpace(cfg.ServiceToken)
	if token == "" || cfg.Timeout <= 0 || c == nil {
		return nil, errors.New("llmgateway: service token, positive timeout and clock are required")
	}
	return &Client{
		endpoint: strings.TrimRight(base.String(), "/") + "/v1/chat/completions",
		token:    token,
		clock:    c,
		http: &http.Client{
			Timeout: cfg.Timeout,
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}, nil
}

// Complete executes a single gateway POST and returns the first choice's text in memory.
// The request ID correlates replays but the gateway can execute and charge each replay.
func (c *Client) Complete(ctx context.Context, g queue.Guarded, in Request) (string, error) {
	if err := g.Err(); err != nil {
		return "", err
	}
	if err := ctx.Err(); err != nil {
		return "", err
	}
	req, err := c.request(ctx, g, in)
	if err != nil {
		return "", err
	}
	text, err := c.send(req)
	if guardErr := g.Err(); guardErr != nil {
		return "", guardErr
	}
	if ctxErr := ctx.Err(); ctxErr != nil {
		return "", ctxErr
	}
	return text, err
}

// ErrNotCommitted means the gateway cannot supply a previously committed completion.
var ErrNotCommitted = errors.New("llmgateway: committed completion lookup unavailable")

// Recover reports that the gateway has no lookup by operation ID, without starting a call.
// The operation must be the one produced by Guarded.Operation for the paid call.
func (c *Client) Recover(ctx context.Context, g queue.Guarded, _ string) (string, error) {
	if err := g.Err(); err != nil {
		return "", err
	}
	if err := ctx.Err(); err != nil {
		return "", err
	}
	return "", ErrNotCommitted
}
