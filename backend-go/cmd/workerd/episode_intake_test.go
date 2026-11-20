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
