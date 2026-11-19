package llmgateway

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	idempotencyHeader = "Idempotency-Key"
	idempotencyAck    = "X-Omi-Idempotency-Key"
)

type message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type completionRequest struct {
	Model          string          `json:"model"`
	Messages       []message       `json:"messages"`
	Stream         bool            `json:"stream"`
	ResponseFormat *responseFormat `json:"response_format,omitempty"`
	Metadata       metadata        `json:"metadata"`
}

type metadata struct {
	Feature       Feature `json:"omi_feature"`
	PromptVersion string  `json:"prompt_version,omitempty"`
	ParserVersion string  `json:"parser_version,omitempty"`
}

type responseFormat struct {
	Type       string     `json:"type"`
	JSONSchema schemaWire `json:"json_schema"`
}

type schemaWire struct {
	Name   string          `json:"name"`
	Strict bool            `json:"strict"`
	Schema json.RawMessage `json:"schema"`
}

func (f Feature) lane() string {
	switch f {
	case ConversationStructure, ConversationDiscard, ConversationActions, ConversationFolder,
		ConversationAppSelect, ConversationAppResult, ExternalStructure, ConversationV3Summary, Memories, MemoryL1:
		return "omi:auto:" + strings.ReplaceAll(string(f), "_", "-")
	case StructureShadow, ActionsShadow:
		return "omi:auto:chat-structured"
	}
	return ""
}

func (c *Client) request(ctx context.Context, g queue.Guarded, in Request) (*http.Request, error) {
	lane := in.Feature.lane()
	if strings.TrimSpace(in.Step) == "" || lane == "" || len(in.Messages) == 0 {
		return nil, classify(CauseRejected, 0, 0)
	}
	payload, err := buildPayload(in, lane)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint, bytes.NewReader(payload))
	if err != nil {
		return nil, classify(CauseRejected, 0, 0)
	}
	// Keep retries under the queue's attempt budget, including when the transport sees the key.
	req.GetBody = nil
	req.Header.Set("Content-Type", "application/json")
	c.authorize(req, g.Tenant())
	key := requestID(g.Operation(in.Step))
	req.Header.Set(idempotencyHeader, key)
	req.Header.Set("X-Omi-Request-Id", key)
	req.Header.Set("X-Omi-LLM-Feature", string(payloadFeature(in)))
	switch platform := strings.ToLower(strings.TrimSpace(in.AppPlatform)); platform {
	case "desktop", "mobile", "web":
		req.Header.Set("X-Omi-App-Platform", platform)
	}
	if err := setBYOK(req, in); err != nil {
		return nil, err
	}
	return req, nil
}

func (c *Client) authorize(req *http.Request, tenant string) {
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("X-Omi-Service-Caller", "backend")
	req.Header.Set("X-Omi-User-Uid", tenant)
}

func payloadFeature(in Request) Feature {
	if in.UsageFeature != "" {
		return in.UsageFeature
	}
	if in.Feature == MemoryL1 {
		return Memories
	}
	if in.Feature == ExternalStructure || in.Feature == ConversationV3Summary {
		return ConversationStructure
	}
	return in.Feature
}

func buildPayload(in Request, lane string) ([]byte, error) {
	body := completionRequest{Model: lane, Metadata: metadata{Feature: payloadFeature(in)}}
	for _, msg := range in.Messages {
		body.Messages = append(body.Messages, message{Role: msg.Role, Content: msg.Text})
	}
	if in.Feature == StructureShadow || in.Feature == ActionsShadow {
		if in.Schema == nil {
			return nil, classify(CauseRejected, 0, 0)
		}
		body.Metadata = metadata{
			Feature:       in.Feature,
			PromptVersion: string(in.Feature) + ".v1",
			ParserVersion: in.Schema.Name + ".v1",
		}
	}
	if in.Schema != nil {
		schema := bytes.TrimSpace(in.Schema.JSON)
		if in.Schema.Name == "" || len(schema) == 0 || schema[0] != '{' {
			return nil, classify(CauseRejected, 0, 0)
		}
		body.ResponseFormat = &responseFormat{
			Type:       "json_schema",
			JSONSchema: schemaWire{Name: in.Schema.Name, Strict: true, Schema: schema},
		}
	}
	payload, err := json.Marshal(body)
	if err != nil {
		return nil, classify(CauseRejected, 0, 0)
	}
	return payload, nil
}

func setBYOK(req *http.Request, in Request) error {
	if in.BYOK == nil {
		return nil
	}
	if in.Feature == StructureShadow || in.Feature == ActionsShadow || in.Feature == ConversationV3Summary {
		return classify(CauseBYOK, 0, 0)
	}
	key := strings.TrimSpace(in.BYOK.Key)
	if key == "" {
		return classify(CauseBYOK, 0, 0)
	}
	switch in.BYOK.Provider {
	case BYOKOpenAI, BYOKOpenRouter, BYOKAnthropic:
		req.Header.Set("X-Omi-Byok-"+string(in.BYOK.Provider)+"-Key", key)
		return nil
	}
	return classify(CauseBYOK, 0, 0)
}

// The gateway replaces the queue's op_ form with a random ID. Use a stable RFC 9562
// version 8 UUID derived from it, with a namespace specific to this wire contract.
func requestID(operation string) string {
	hash := sha256.Sum256([]byte("omi:llmgateway:request:v1\x00" + operation))
	hash[6] = hash[6]&0x0f | 0x80
	hash[8] = hash[8]&0x3f | 0x80
	id := hex.EncodeToString(hash[:16])
	return id[:8] + "-" + id[8:12] + "-" + id[12:16] + "-" + id[16:20] + "-" + id[20:]
}

const maxCompletionBytes = 8 << 20

type completionResponse struct {
	Choices []struct {
		FinishReason string `json:"finish_reason"`
		Message      struct {
			Content string `json:"content"`
			Refusal string `json:"refusal"`
		} `json:"message"`
	} `json:"choices"`
}

func (c *Client) send(req *http.Request, key string, lookup bool) (string, error) {
	resp, err := c.http.Do(req)
	if err != nil {
		return "", classify(CauseTransient, 0, 0)
	}
	text, err := c.read(resp, key, lookup)
	if closeErr := resp.Body.Close(); closeErr != nil && err == nil {
		return "", classify(CauseTransient, resp.StatusCode, 0)
	}
	return text, err
}

func (c *Client) read(resp *http.Response, key string, lookup bool) (string, error) {
	if resp.StatusCode != http.StatusOK {
		cause, code := readCause(resp)
		if lookup && (code == "idempotency_not_found" || code == "idempotency_expired" || code == "idempotency_indeterminate") {
			return "", ErrNotCommitted
		}
		delay := httpx.RetryAfter(resp.Header.Get("Retry-After"), c.clock.Now())
		return "", classify(cause, resp.StatusCode, delay)
	}
	if resp.Header.Get(idempotencyAck) != key {
		return "", classify(CauseIndeterminate, resp.StatusCode, 0)
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, maxCompletionBytes+1))
	if err != nil {
		return "", classify(CauseTransient, resp.StatusCode, 0)
	}
	var result completionResponse
	if len(data) > maxCompletionBytes || json.Unmarshal(data, &result) != nil || len(result.Choices) == 0 {
		return "", classify(CauseRejected, resp.StatusCode, 0)
	}
	choice := result.Choices[0]
	if choice.FinishReason == "content_filter" || choice.FinishReason == "length" ||
		choice.Message.Refusal != "" || strings.TrimSpace(choice.Message.Content) == "" {
		return "", classify(CauseRejected, resp.StatusCode, 0)
	}
	return choice.Message.Content, nil
}
