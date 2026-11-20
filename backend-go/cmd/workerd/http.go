package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const probeTimeout = 2 * time.Second

func healthHandler(stopping <-chan struct{}, ready func(context.Context) error) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("GET /ready", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), probeTimeout)
		defer cancel()
		if ready(ctx) != nil {
			http.Error(w, "queue unavailable", http.StatusServiceUnavailable)
			return
		}
		select {
		case <-stopping:
			http.Error(w, "queue unavailable", http.StatusServiceUnavailable)
		default:
			w.WriteHeader(http.StatusOK)
		}
	})
	return mux
}

func newServer(port int, handler http.Handler) *http.Server {
	return &http.Server{
		Addr:              fmt.Sprintf(":%d", port),
		Handler:           handler,
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       5 * time.Second,
		WriteTimeout:      5 * time.Second,
		IdleTimeout:       30 * time.Second,
		MaxHeaderBytes:    16 << 10,
	}
}

// serve owns the workers and their store after startup.
func serve(ctx context.Context, cfg config, store *queue.Store, workers *queue.Workers, registry *prometheus.Registry) error {
	lifetime, cancel := context.WithCancel(ctx)
	defer cancel()
	health := newServer(cfg.healthPort, healthHandler(lifetime.Done(), store.Ready))
	metrics := newServer(cfg.metricsPort, metricsHandler(registry))
	ended := make(chan error, 2)
	go listen(health, "health", ended)
	go listen(metrics, "metrics", ended)

	var serveErr error
	select {
	case <-lifetime.Done():
	case serveErr = <-ended:
	}
	cancel()
	// Workers.Stop cancels active handlers and returns claims that never launched.
	// A queue drain API is needed to preserve active handlers until a grace deadline
	// and release their leases safely at that deadline.
	stopped := make(chan struct{})
	go func() {
		defer close(stopped)
		workers.Stop()
		store.Close()
	}()
	shutdown, end := context.WithTimeout(context.WithoutCancel(ctx), cfg.stopTimeout)
	defer end()
	return errors.Join(serveErr, stopServers(shutdown, stopped, health, metrics))
}

func stopServers(ctx context.Context, stopped <-chan struct{}, health, metrics *http.Server) error {
	healthErr := health.Shutdown(ctx)
	metricsErr := metrics.Shutdown(ctx)
	select {
	case <-stopped:
		return errors.Join(healthErr, metricsErr)
	case <-ctx.Done():
		return errors.Join(healthErr, metricsErr, errors.New("worker shutdown deadline elapsed"))
	}
}

func listen(server *http.Server, name string, ended chan<- error) {
	err := server.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		ended <- nil
		return
	}
	ended <- fmt.Errorf("%s listener failed: %w", name, err)
}
