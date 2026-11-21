package main

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func TestServeReturnsCleanlyAfterContextCancellation(t *testing.T) {
	t.Parallel()
	h := queuetest.Open(t, queuetest.Policy(), testKind())
	workers := h.Start(nil)
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	cfg := serveTestConfig(t)
	done := make(chan error, 1)
	started, stopped := make(chan struct{}), make(chan struct{})
	maintenance := func(ctx context.Context) {
		close(started)
		<-ctx.Done()
		close(stopped)
	}
	go func() {
		done <- serve(ctx, cfg, h.Store, workers, prometheus.NewRegistry(), maintenance, nil)
	}()

	waitForHealth(t, cfg.healthPort)
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("maintenance did not start")
	}
	cancel()
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("serve after cancellation: %v", err)
		}
		select {
		case <-stopped:
		default:
			t.Fatal("serve returned before maintenance stopped")
		}
	case <-time.After(3 * time.Second):
		t.Fatal("serve did not stop before its shutdown deadline")
	}
}

func TestServeReturnsListenerFailure(t *testing.T) {
	t.Parallel()
	h := queuetest.Open(t, queuetest.Policy(), testKind())
	workers := h.Start(nil)
	var listenConfig net.ListenConfig
	occupied, err := listenConfig.Listen(t.Context(), "tcp", ":0")
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if closeErr := occupied.Close(); closeErr != nil {
			t.Errorf("close occupied listener: %v", closeErr)
		}
	}()
	address, ok := occupied.Addr().(*net.TCPAddr)
	if !ok {
		t.Fatalf("occupied listener address has type %T", occupied.Addr())
	}
	port := address.Port
	cfg := serveTestConfig(t)
	cfg.healthPort = port
	err = serve(t.Context(), cfg, h.Store, workers, prometheus.NewRegistry(), nil, nil)
	if err == nil || !strings.Contains(err.Error(), "health listener failed") {
		t.Fatalf("serve error = %v, want health listener failure", err)
	}
}

func TestStopServersReportsWorkerShutdownDeadline(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	stopped := make(chan struct{})
	err := stopServers(ctx, stopped, newServer(0, http.NotFoundHandler()), newServer(0, http.NotFoundHandler()))
	if err == nil || !strings.Contains(err.Error(), "worker shutdown deadline elapsed") {
		t.Fatalf("shutdown error = %v, want worker deadline", err)
	}
}

func serveTestConfig(t *testing.T) config {
	t.Helper()
	healthPort := freePort(t)
	metricsPort := freePort(t)
	for metricsPort == healthPort {
		metricsPort = freePort(t)
	}
	return config{
		healthPort:  healthPort,
		metricsPort: metricsPort,
		stopTimeout: time.Second,
	}
}

func freePort(t *testing.T) int {
	t.Helper()
	var listenConfig net.ListenConfig
	listener, err := listenConfig.Listen(t.Context(), "tcp", ":0")
	if err != nil {
		t.Fatal(err)
	}
	address, ok := listener.Addr().(*net.TCPAddr)
	if !ok {
		t.Fatalf("listener address has type %T", listener.Addr())
	}
	port := address.Port
	if err := listener.Close(); err != nil {
		t.Fatal(err)
	}
	return port
}

func waitForHealth(t *testing.T, port int) {
	t.Helper()
	ctx, cancel := context.WithTimeout(t.Context(), 3*time.Second)
	defer cancel()
	client := &http.Client{Timeout: 100 * time.Millisecond}
	url := fmt.Sprintf("http://127.0.0.1:%d/health", port)
	for {
		request, requestErr := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if requestErr != nil {
			t.Fatal(requestErr)
		}
		response, err := client.Do(request)
		if err == nil {
			if closeErr := response.Body.Close(); closeErr != nil {
				t.Fatalf("close health response: %v", closeErr)
			}
			if response.StatusCode == http.StatusOK {
				return
			}
		}
		select {
		case <-ctx.Done():
			t.Fatalf("health listener did not start: %v", err)
		case <-time.After(10 * time.Millisecond):
		}
	}
}
