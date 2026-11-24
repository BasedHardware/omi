package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"google.golang.org/api/idtoken"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
)

func reportReplayStatus(t *testing.T, family *finalization.Service, intent finalization.Intent, phase string) {
	t.Helper()
	body := fmt.Sprintf(`{"owner":%q,"conversation":%q,"job":%q,"revision":%d}`,
		intent.Ref.Owner, intent.Ref.ID, intent.JobID, intent.Revision)
	req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, finalizationStatusPath, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer replay-only")
	rec := httptest.NewRecorder()
	handler := finalizationStatusEndpoint{
		audience: "fixture", caller: "fixture", lookup: family.Status,
		slots: make(chan struct{}, finalizationStatusReaders),
		validate: func(_ context.Context, token, audience string) (*idtoken.Payload, error) {
			if token != "replay-only" || audience != "fixture" {
				t.Fatal("invalid fixture authorization")
			}
			return &idtoken.Payload{Issuer: "accounts.google.com", Claims: map[string]any{
				"email": "fixture", "email_verified": true,
			}}, nil
		},
	}
	requestWithoutToken := req.Clone(t.Context())
	requestWithoutToken.Header.Del("Authorization")
	handler.ServeHTTP(rec, requestWithoutToken)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("unauthenticated status request returned %d", rec.Code)
	}
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("private finalization status returned %d", rec.Code)
	}
	fmt.Printf("FINALIZATION_STATUS_%s=%s\n", phase, strings.TrimSpace(rec.Body.String()))
}
