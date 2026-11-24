package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const probeTimeout = 2 * time.Second

func healthHandler(stopping <-chan struct{}, ready func(context.Context) error, intake http.Handler) *http.ServeMux {
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
	if intake != nil {
		mux.Handle("/internal/finalization/", intake)
	}
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
func serve(ctx context.Context, cfg config, store *queue.Store, workers *queue.Workers, registry *prometheus.Registry, maintenance func(context.Context), intake http.Handler, extra ...*http.Server) error {
	lifetime, cancel := context.WithCancel(ctx)
	defer cancel()
	var maintenanceGroup sync.WaitGroup
	if maintenance != nil {
		maintenanceGroup.Go(func() { maintenance(lifetime) })
	}
	mux := healthHandler(lifetime.Done(), store.Ready, intake)
	health := newServer(cfg.healthPort, mux)
	metrics := newServer(cfg.metricsPort, metricsHandler(registry))
	ended := make(chan error, 2+len(extra))
	go listen(health, "health", ended)
	go listen(metrics, "metrics", ended)
	servers := []*http.Server{health, metrics}
	for _, server := range extra {
		if server != nil {
			servers = append(servers, server)
			go listenErase(server, cfg.erase, ended)
		}
	}

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
		maintenanceGroup.Wait()
		store.Close()
	}()
	shutdown, end := context.WithTimeout(context.WithoutCancel(ctx), cfg.stopTimeout)
	defer end()
	return errors.Join(serveErr, stopServers(shutdown, stopped, servers...))
}

func stopServers(ctx context.Context, stopped <-chan struct{}, servers ...*http.Server) error {
	var shutdownErr error
	for _, server := range servers {
		shutdownErr = errors.Join(shutdownErr, server.Shutdown(ctx))
	}
	select {
	case <-stopped:
		return shutdownErr
	case <-ctx.Done():
		return errors.Join(shutdownErr, errors.New("worker shutdown deadline elapsed"))
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

func listenErase(server *http.Server, cfg eraseConfig, ended chan<- error) {
	err := server.ListenAndServeTLS(cfg.cert, cfg.key)
	if errors.Is(err, http.ErrServerClosed) {
		ended <- nil
		return
	}
	ended <- fmt.Errorf("queue erase TLS listener failed: %w", err)
}
