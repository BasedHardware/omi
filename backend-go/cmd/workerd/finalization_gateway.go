package main

import (
	"context"
	"errors"
	"strconv"
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/llmgateway"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// readFinalizationGateway requires a separate opt-in for the keyed notes route.
func (c *config) readFinalizationGateway(lookup lookupEnv) error {
	raw, set := lookup("WORKER_FINALIZATION_GATEWAY_ENABLED")
	if !set {
		return nil
	}
	enabled, err := strconv.ParseBool(raw)
	if err != nil {
		return errors.New("WORKER_FINALIZATION_GATEWAY_ENABLED must be a boolean")
	}
	if !enabled {
		return nil
	}
	baseURL, _ := lookup("OMI_LLM_GATEWAY_URL")
	token, _ := lookup("OMI_LLM_GATEWAY_SERVICE_TOKEN")
	if strings.TrimSpace(token) == "" {
		token, _ = lookup("LLM_GATEWAY_SERVICE_TOKEN")
	}
	baseURL, token = strings.TrimSpace(baseURL), strings.TrimSpace(token)
	if baseURL == "" || token == "" {
		return errors.New("finalization gateway requires OMI_LLM_GATEWAY_URL and a gateway service token")
	}
	c.gateway = llmgateway.Config{
		BaseURL: baseURL, ServiceToken: token, Timeout: 60 * time.Second,
		IdleConnections: c.policy.Workers,
	}
	return nil
}

func (m *finalizationRuntime) bindFinalizationGateway(cfg llmgateway.Config, clk clock.Clock) error {
	if cfg.BaseURL == "" {
		return nil
	}
	client, err := llmgateway.New(cfg, clk)
	if err != nil {
		return err
	}
	m.gateway = client
	m.family.Gateway = finalizationGateway{client: client}
	return nil
}

// finalizationGateway maps the notes port to the keyed submission and recovery pair.
type finalizationGateway struct {
	client llmgateway.Replayable
}

func (finalizationGateway) OperationID(g queue.Guarded, step string) string {
	return llmgateway.OperationID(g, step)
}

func (f finalizationGateway) Complete(ctx context.Context, g queue.Guarded, req finalization.CompletionRequest) (string, error) {
	messages := make([]llmgateway.Message, len(req.Messages))
	for i, message := range req.Messages {
		messages[i] = llmgateway.Message(message)
	}
	in := llmgateway.Request{
		Step: req.Step, JobCreatedAt: req.JobCreatedAt, Feature: llmgateway.Feature(req.Feature),
		Messages: messages, AppPlatform: req.AppPlatform,
	}
	if req.BYOK != nil {
		in.BYOK = &llmgateway.BYOK{Provider: llmgateway.BYOKProvider(req.BYOK.Provider), Key: req.BYOK.Key}
	}
	return f.client.Complete(ctx, g, in)
}

func (f finalizationGateway) Recover(ctx context.Context, g queue.Guarded, step string) (string, error) {
	text, err := f.client.Recover(ctx, g, step)
	if errors.Is(err, llmgateway.ErrNotCommitted) {
		return "", finalization.ErrCompletionAbsent
	}
	return text, err
}
