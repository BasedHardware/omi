package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"google.golang.org/api/idtoken"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
)

func TestEpisodeIntakeRequiresConfiguredWorkloadAndForwardsVersion(t *testing.T) {
	t.Parallel()
	calls := 0
	endpoint := episodeIntakeEndpoint{
		audience: "fixture-audience", caller: "sync@fixture.iam.gserviceaccount.com",
		validate: func(_ context.Context, token, audience string) (*idtoken.Payload, error) {
			if audience != "fixture-audience" {
				t.Fatal("wrong audience")
			}
			return &idtoken.Payload{
				Issuer: "https://accounts.google.com",
				Claims: map[string]any{"email": "sync@fixture.iam.gserviceaccount.com", "email_verified": token == "valid"},
			}, nil
		},
		attach: func(_ context.Context, ref finalization.Ref, written time.Time) (string, error) {
			calls++
			if ref.Owner != "owner" || ref.ID != "clip" || written.Unix() != 1 {
				t.Fatal("wrong intake receipt")
			}
			return "episode", nil
		},
	}
	for _, row := range []struct {
		token string
		want  int
	}{{"wrong", http.StatusForbidden}, {"valid", http.StatusOK}} {
		req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, episodeIntakePath, strings.NewReader(
			`{"owner":"owner","conversation":"clip","written":"1970-01-01T00:00:01Z"}`))
		req.Header.Set("Authorization", "Bearer "+row.token)
		response := httptest.NewRecorder()
		endpoint.ServeHTTP(response, req)
		if response.Code != row.want {
			t.Fatalf("got %d, want %d", response.Code, row.want)
		}
	}
	if calls != 1 {
		t.Fatalf("received %d callbacks", calls)
	}
}

func TestEpisodeIntakeHandlerRequiresBothIdentitySettings(t *testing.T) {
	t.Parallel()
	runtime := finalizationRuntime{family: &finalization.Service{}}
	for _, cfg := range []config{
		{},
		{episodeIntakeAudience: "fixture-audience"},
		{episodeIntakeCaller: "sync@fixture.iam.gserviceaccount.com"},
	} {
		if runtime.episodeIntakeHandler(cfg) != nil {
			t.Fatal("incomplete identity configured an intake handler")
		}
	}
}

func TestEpisodeIntakeRejectsInvalidBodySuffix(t *testing.T) {
	t.Parallel()
	const body = `{"owner":"owner","conversation":"clip","written":"1970-01-01T00:00:01Z"}`
	const caller = "sync@fixture.iam.gserviceaccount.com"
	endpoint := episodeIntakeEndpoint{
		caller: caller,
		validate: func(context.Context, string, string) (*idtoken.Payload, error) {
			return &idtoken.Payload{
				Issuer: "https://accounts.google.com",
				Claims: map[string]any{"email": caller, "email_verified": true},
			}, nil
		},
	}
	for _, test := range []struct {
		name   string
		suffix string
	}{
		{"trailing JSON value", " {}"},
		{"oversized whitespace after valid JSON", strings.Repeat(" ", 2049-len(body))},
	} {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, episodeIntakePath, strings.NewReader(body+test.suffix))
			req.Header.Set("Authorization", "Bearer valid")
			response := httptest.NewRecorder()
			endpoint.ServeHTTP(response, req)
			if response.Code != http.StatusBadRequest {
				t.Fatalf("got %d, want %d", response.Code, http.StatusBadRequest)
			}
		})
	}
}
