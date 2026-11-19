package main

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type markerReaderFunc func(context.Context, string) (map[string]any, error)

func (f markerReaderFunc) ReadDeletionMarker(ctx context.Context, owner string) (map[string]any, error) {
	return f(ctx, owner)
}

func TestEraseRequiresAuthenticatedArmedGenerationAndCommit(t *testing.T) {
	t.Parallel()
	claim := strings.Repeat("b", 64)
	for _, tc := range []struct {
		name, token, status, jobID string
		eraseErr                   error
		want                       int
		calls                      int
	}{
		{"wrong identity", "bad", "running", "job", nil, http.StatusUnauthorized, 0},
		{"grace pending", "trusted", "pending_deletion", "job", nil, http.StatusConflict, 0},
		{"stale generation", "trusted", "running", "old", nil, http.StatusConflict, 0},
		{"uncommitted erase", "trusted", "running", "job", errors.New("database failure"), http.StatusServiceUnavailable, 1},
		{"committed erase", "trusted", "running", "job", nil, http.StatusOK, 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			calls := 0
			endpoint := eraseEndpoint{
				authorize: func(_ context.Context, token string) error {
					if token != "trusted" {
						return errors.New("cannot authenticate")
					}
					return nil
				},
				markers: markerReaderFunc(func(_ context.Context, owner string) (map[string]any, error) {
					if owner != "test-tenant" {
						t.Fatalf("marker read for %q", owner)
					}
					return map[string]any{
						"wipe_status": tc.status, "wipe_job_id": tc.jobID,
						"go_queue_erase_claim": claim, "go_queue_erase_armed_at": time.Unix(1, 0),
					}, nil
				}),
				erase: func(_ context.Context, owner string) error {
					calls++
					if owner != "test-tenant" {
						t.Fatalf("erase for %q", owner)
					}
					return tc.eraseErr
				},
				report: func(error) {},
			}
			body := `{"tenant":"test-tenant","wipe_job_id":"job","claim":"` + claim + `"}`
			req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, erasePath, strings.NewReader(body))
			req.Header.Set("Authorization", "Bearer "+tc.token)
			rec := httptest.NewRecorder()
			endpoint.routes().ServeHTTP(rec, req)
			if rec.Code != tc.want || calls != tc.calls {
				t.Fatalf("status and calls = %d/%d, want %d/%d", rec.Code, calls, tc.want, tc.calls)
			}
			if tc.want == http.StatusOK && !strings.Contains(rec.Body.String(), `"wipe_job_id":"job","claim":"`+claim) {
				t.Fatal("successful erase must return a receipt for the requesting generation and claim")
			}
		})
	}
}
