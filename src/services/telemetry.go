package services

import (
	"context"
	"errors"
	"time"

	"github.com/segmentio/ksuid"
)

// TelemetryService handles product event emission.
type TelemetryService interface {
	EmitProductEventAsync(ctx context.Context, req FeedbackRequest) error
}

// PostHogTelemetry implements TelemetryService with async emission.
type PostHogTelemetry struct {
	client PostHogClient
}

// EmitProductEventAsync emits telemetry asynchronously with error isolation.
func (p *PostHogTelemetry) EmitProductEventAsync(ctx context.Context, req FeedbackRequest) error {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()

	// Non-blocking emission
	go func() {
		if err := p.client.Emit(ctx, "mobile_feedback", map[string]interface{} {
			"id":       req.ID,
			"rating":   req.Rating,
			"feedback": req.Feedback,
			"type":     req.SessionType,
		}); err != nil {
			// Log but do not propagate
		}
	}()

	return nil
}

// PostHogClient is a mock interface for PostHog client.
type PostHogClient interface {
	Emit(ctx context.Context, event string, properties map[string]interface{}) error
}