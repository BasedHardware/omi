package handlers_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

func TestFeedbackHandler(t *testing.T) {
	tests := []struct {
		name           string
		body           string
		statusExpected int
	} {
		{"ValidFeedback", `{"id":"123","rating":5,"feedback":"Good","session_type":"conversation"}`, http.StatusCreated},
		{"EmptyID", `{"id":"","rating":5,"session_type":"conversation"}`, http.StatusUnprocessableEntity},
		{"WhitespaceID", `{"id":"   ","rating":5,"session_type":"conversation"}`, http.StatusUnprocessableEntity},
		{"DBFailure", `{"id":"fail123","rating":5,"session_type":"conversation"}`, http.StatusServiceUnavailable},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			router := gin.Default()
			router.POST("/feedback", FeedbackHandler)
			router.Use(func(c *gin.Context) {
				c.Set("logger", zap.NewExample())
				c.Set("telemetry", &MockTelemetry{})
			})

			req := httptest.NewRequest(http.MethodPost, "/feedback", bytes.NewBufferString(tt.body))
			req.Header.Set("Content-Type", "application/json")

			w := httptest.NewRecorder()
			router.ServeHTTP(w, req)

			if w.Code != tt.statusExpected {
				t.Errorf("Expected status %d, got %d", tt.statusExpected, w.Code)
			}
		})
	}
}

// MockTelemetry satisfies TelemetryService for testing.
type MockTelemetry struct{}

func (m *MockTelemetry) EmitProductEventAsync(ctx context.Context, req FeedbackRequest) error {
	return nil
}