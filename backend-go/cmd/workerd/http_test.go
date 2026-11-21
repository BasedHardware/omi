package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func TestHealthRoutesAndReadinessFollowQueueSchemaAndShutdown(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	store, err := queue.Open(ctx, pgtest.New(t), queuetest.Policy(), nil, nil, clock.System{})
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	health := healthHandler(ctx.Done(), store.Ready, nil)
	assertStatus(t, health, http.MethodGet, "/health", http.StatusOK)
	assertStatus(t, health, http.MethodGet, "/ready", http.StatusServiceUnavailable)
	assertStatus(t, health, http.MethodGet, "/metrics", http.StatusNotFound)
	assertStatus(t, health, http.MethodPost, "/jobs", http.StatusNotFound)
	assertStatus(t, health, http.MethodPost, "/ready", http.StatusMethodNotAllowed)

	if migrationErr := store.Migrate(ctx); migrationErr != nil {
		t.Fatal(migrationErr)
	}
	assertStatus(t, health, http.MethodGet, "/ready", http.StatusOK)
	cancel()
	assertStatus(t, health, http.MethodGet, "/ready", http.StatusServiceUnavailable)
	assertStatus(t, health, http.MethodGet, "/health", http.StatusOK)
}

func assertStatus(t *testing.T, handler http.Handler, method, path string, want int) {
	t.Helper()
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequestWithContext(t.Context(), method, path, nil))
	if response.Code != want {
		t.Errorf("%s %s status = %d, want %d", method, path, response.Code, want)
	}
}

func TestHealthMuxRoutesEpisodeIntakeOnlyWhenEnabled(t *testing.T) {
	t.Parallel()
	runtime := finalizationRuntime{}
	disabled := healthHandler(nil, nil, runtime.episodeIntakeHandler(config{}))
	assertStatus(t, disabled, http.MethodPost, episodeIntakePath, http.StatusNotFound)

	enabled := healthHandler(nil, nil, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	assertStatus(t, enabled, http.MethodGet, episodeIntakePath, http.StatusMethodNotAllowed)
	assertStatus(t, enabled, http.MethodPost, episodeIntakePath, http.StatusNoContent)
}
