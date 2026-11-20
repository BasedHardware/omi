package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

func testKind() queue.Kind {
	return queue.Kind{Name: "example", Formats: []int{1}, Steps: []string{"call"}, Causes: []queue.Cause{"declared"}}
}

func TestQueueObserverUsesOnlyDeclaredLabels(t *testing.T) {
	t.Parallel()
	registry := prometheus.NewRegistry()
	m := newQueueMetrics(registry, []queue.Kind{testKind()}, gateAbandoned)
	m.Outcome("example", queue.TerminalSuccess, queue.CauseNone)
	m.Outcome("private-kind", "private-result", "private-cause")
	m.Retry("example", "declared")
	m.Yield("private-kind", "private-cause")
	m.BudgetRequeue(gateAbandoned)
	m.Step("example", "call", 250*time.Millisecond)
	m.Step("example", "private-step", 500*time.Millisecond)

	body := scrape(t, metricsHandler(registry))
	if strings.Contains(body, "private-") {
		t.Fatal("metrics leaked an undeclared label")
	}
	for _, want := range []string{
		`omi_queue_outcomes_total{cause="none",kind="example",outcome="success"} 1`,
		`omi_queue_outcomes_total{cause="unknown",kind="unknown",outcome="unknown"} 1`,
		`omi_queue_retries_total{cause="declared",kind="example"} 1`,
		`omi_queue_yields_total{cause="unknown",kind="unknown"} 1`,
		`omi_queue_budget_requeues_total{cause="gate_abandoned"} 1`,
		`omi_queue_step_duration_seconds_sum{kind="example",step="call"} 0.25`,
		`omi_queue_step_duration_seconds_count{kind="example",step="unknown"} 1`,
	} {
		if !strings.Contains(body, want) {
			t.Errorf("metrics missing %q", want)
		}
	}
}

func TestMetricsScrapeCountsJobsWithNoHandler(t *testing.T) {
	t.Parallel()
	h := queuetest.Open(t, queuetest.Policy(), testKind())
	workers := h.Start(nil)
	registry := prometheus.NewRegistry()
	registry.MustRegister(newStrandedCollector(workers))
	mux := metricsHandler(registry)
	assertStatus(t, mux, http.MethodGet, "/health", http.StatusNotFound)
	assertStatus(t, mux, http.MethodGet, "/ready", http.StatusNotFound)
	assertGauge(t, mux, "0")

	_, err := h.Store.Enqueue(t.Context(), queue.NewJob{
		Key: "queued-job", Tenant: "test-tenant", Kind: "example", Format: 1,
		Step: "call", Meta: []byte(`{}`), RunAt: time.Now().Add(-time.Minute),
	})
	if err != nil {
		t.Fatal(err)
	}
	assertGauge(t, mux, "1")

	workers.Stop()
	h.Store.Close()
	assertStatus(t, mux, http.MethodGet, "/metrics", http.StatusInternalServerError)
}

func assertGauge(t *testing.T, handler http.Handler, want string) {
	t.Helper()
	body := scrape(t, handler)
	if !strings.Contains(body, "# TYPE omi_queue_stranded_jobs gauge\n") ||
		!strings.Contains(body, "omi_queue_stranded_jobs "+want+"\n") ||
		!strings.Contains(body, "# TYPE omi_queue_stranded_oldest_due_seconds gauge\n") {
		t.Fatalf("expected stranded gauge of %s, got %s", want, body)
	}
}

func scrape(t *testing.T, handler http.Handler) string {
	t.Helper()
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/metrics", nil))
	if response.Code != http.StatusOK {
		t.Fatalf("scrape status = %d", response.Code)
	}
	return response.Body.String()
}
