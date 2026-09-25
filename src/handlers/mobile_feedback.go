package handlers

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

// FeedbackRequest defines the mobile feedback payload structure.
type FeedbackRequest struct {
	ID          string `json:"id" binding:"required"`
	Rating      int    `json:"rating" binding:"required,min=1,max=5"`
	Feedback    string `json:"feedback"`
	SessionType string `json:"session_type" binding:"required,oneof=conversation recording"`
}

// FeedbackHandler processes mobile feedback with sanitized error handling.
func FeedbackHandler(c *gin.Context) {
	logger := c.MustGet("logger").(*zap.Logger)
	telemetry := c.MustGet("telemetry").(TelemetryService)

	var req FeedbackRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid payload"})
		return
	}

	// Validate ID strictly
	if strings.TrimSpace(req.ID) == "" {
		c.JSON(http.StatusUnprocessableEntity, gin.H{"error": "ID cannot be empty or whitespace"})
		return
	}

	// Process feedback with error isolation
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	go func() {
		if err := telemetry.EmitProductEventAsync(ctx, req); err != nil {
			logger.Warn("Telemetry emission failed", zap.Error(err))
		}
	}()

	// Attempt storage with fallback
	if err := storeFeedback(ctx, req); err != nil {
		if errors.Is(err, ErrDatabaseUnavailable) {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Service temporarily unavailable"})
		} else {
			logger.Error("Feedback storage failed", zap.Error(err))
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Internal server error"})
		}
		return
	}

	c.JSON(http.StatusCreated, gin.H{"status": "Feedback received"})
}

// storeFeedback attempts to persist feedback with error isolation.
func storeFeedback(ctx context.Context, req FeedbackRequest) error {
	// Simulate DB operation with potential failures
	if strings.Contains(req.ID, "fail") {
		return ErrDatabaseUnavailable
	}

	// Actual storage logic would go here
	return nil
}

// ErrDatabaseUnavailable indicates temporary DB connectivity issues.
var ErrDatabaseUnavailable = errors.New("database unavailable")