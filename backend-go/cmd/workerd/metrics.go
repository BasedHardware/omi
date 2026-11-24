package main

import (
	"context"
	"errors"
	"net/http"
	"slices"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type queueMetrics struct {
	releaseLag prometheus.Histogram
	outcomes   *prometheus.CounterVec
	retries    *prometheus.CounterVec
	yields     *prometheus.CounterVec
	requeues   *prometheus.CounterVec
	steps      *prometheus.HistogramVec
	declared   map[string][]string
	causes     map[queue.Cause]bool
}

func newQueueMetrics(registry *prometheus.Registry, kinds []queue.Kind, gateCause queue.Cause) *queueMetrics {
	m := &queueMetrics{
		releaseLag: prometheus.NewHistogram(prometheus.HistogramOpts{Name: "omi_queue_entitlement_release_seconds", Help: "Seconds from funding change to committed release of eligible work.", Buckets: []float64{1, 5, 15, 30, 60, 120, 300, 3600}}),
		outcomes:   counter("outcomes", "Terminal queue outcomes.", "kind", "outcome", "cause"),
		retries:    counter("retries", "Failed attempts scheduled for retry.", "kind", "cause"),
		yields:     counter("yields", "Deferrals that refunded an attempt.", "kind", "cause"),
		requeues:   counter("budget_requeues", "Automatic requeues after attempt exhaustion.", "cause"),
		steps: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Namespace: "omi", Subsystem: "queue", Name: "step_duration_seconds",
			Help: "Time spent in a declared queue step.", Buckets: prometheus.DefBuckets,
		}, []string{"kind", "step"}),
		declared: make(map[string][]string, len(kinds)),
		causes:   make(map[queue.Cause]bool),
	}
	for _, cause := range []queue.Cause{
		queue.CauseNone, queue.CauseLeaseExpired, queue.CauseHandlerPanic,
		queue.CauseReconcileExhausted, queue.CauseUnknown, gateCause,
	} {
		m.causes[cause] = true
	}
	for _, kind := range kinds {
		m.declared[kind.Name] = slices.Clone(kind.Steps)
		for _, cause := range kind.Causes {
			m.causes[cause] = true
		}
	}
	registry.MustRegister(m.outcomes, m.retries, m.yields, m.requeues, m.steps, m.releaseLag)
	return m
}

func counter(name, help string, labels ...string) *prometheus.CounterVec {
	return prometheus.NewCounterVec(prometheus.CounterOpts{
		Namespace: "omi", Subsystem: "queue", Name: name + "_total", Help: help,
	}, labels)
}

const unknown = "unknown"

func (m *queueMetrics) kindLabel(kind string) string {
	if _, ok := m.declared[kind]; ok {
		return kind
	}
	return unknown
}

func (m *queueMetrics) causeLabel(cause queue.Cause) string {
	if m.causes[cause] {
		return string(cause)
	}
	return unknown
}

func (m *queueMetrics) EntitlementReleased(d time.Duration) { m.releaseLag.Observe(d.Seconds()) }

func (m *queueMetrics) Outcome(kind string, outcome queue.Terminal, cause queue.Cause) {
	label := unknown
	if slices.Contains(queue.Terminals(), outcome) {
		label = string(outcome)
	}
	m.outcomes.WithLabelValues(m.kindLabel(kind), label, m.causeLabel(cause)).Inc()
}

func (m *queueMetrics) Retry(kind string, cause queue.Cause) {
	m.retries.WithLabelValues(m.kindLabel(kind), m.causeLabel(cause)).Inc()
}

func (m *queueMetrics) Yield(kind string, cause queue.Cause) {
	m.yields.WithLabelValues(m.kindLabel(kind), m.causeLabel(cause)).Inc()
}

func (m *queueMetrics) BudgetRequeue(cause queue.Cause) {
	m.requeues.WithLabelValues(m.causeLabel(cause)).Inc()
}

func (m *queueMetrics) Step(kind, step string, duration time.Duration) {
	if !slices.Contains(m.declared[kind], step) {
		step = unknown
	}
	m.steps.WithLabelValues(m.kindLabel(kind), step).Observe(duration.Seconds())
}

type strandedCollector struct {
	count, oldest *prometheus.Desc
	read          func(context.Context) (int64, float64, error)
}

func newStrandedCollector(workers *queue.Workers) strandedCollector {
	return strandedCollector{
		count: prometheus.NewDesc("omi_queue_stranded_jobs",
			"Due jobs this replica cannot claim.", nil, nil),
		oldest: prometheus.NewDesc("omi_queue_stranded_oldest_due_seconds",
			"Seconds the oldest stranded job has been due on this replica.", nil, nil),
		read: workers.Stranded,
	}
}

func (c strandedCollector) Describe(ch chan<- *prometheus.Desc) {
	ch <- c.count
	ch <- c.oldest
}

func (c strandedCollector) Collect(ch chan<- prometheus.Metric) {
	// Prometheus collectors do not receive the request context.
	ctx, cancel := context.WithTimeout(context.Background(), probeTimeout)
	defer cancel()
	count, oldest, err := c.read(ctx)
	if err != nil {
		ch <- prometheus.NewInvalidMetric(c.count, errors.New("stranded queue query failed"))
		return
	}
	ch <- prometheus.MustNewConstMetric(c.count, prometheus.GaugeValue, float64(count))
	ch <- prometheus.MustNewConstMetric(c.oldest, prometheus.GaugeValue, oldest)
}

func metricsHandler(registry *prometheus.Registry) *http.ServeMux {
	mux := http.NewServeMux()
	mux.Handle("GET /metrics", promhttp.HandlerFor(registry, promhttp.HandlerOpts{MaxRequestsInFlight: 2}))
	return mux
}

type customerWaitCollector struct {
	store                           *queue.Store
	owners, units, seconds, expired *prometheus.Desc
}

func newCustomerWaitCollector(store *queue.Store) customerWaitCollector {
	return customerWaitCollector{store: store,
		owners:  prometheus.NewDesc("omi_queue_waiting_on_customer_owners", "Owners waiting on funding.", nil, nil),
		units:   prometheus.NewDesc("omi_queue_waiting_on_customer_units", "Units waiting on funding.", nil, nil),
		seconds: prometheus.NewDesc("omi_queue_waiting_on_customer_audio_seconds", "Audio seconds waiting on funding.", nil, nil),
		expired: prometheus.NewDesc("omi_queue_expired_unfunded_total", "Units settled after custody expired while unfunded.", nil, nil)}
}

func (c customerWaitCollector) Describe(ch chan<- *prometheus.Desc) {
	ch <- c.owners
	ch <- c.units
	ch <- c.seconds
	ch <- c.expired
}

func (c customerWaitCollector) Collect(ch chan<- prometheus.Metric) {
	ctx, cancel := context.WithTimeout(context.Background(), probeTimeout)
	defer cancel()
	w, err := c.store.WaitingOnCustomer(ctx)
	if err != nil {
		ch <- prometheus.NewInvalidMetric(c.units, errors.New("customer wait query failed"))
		return
	}
	ch <- prometheus.MustNewConstMetric(c.owners, prometheus.GaugeValue, float64(w.Owners))
	ch <- prometheus.MustNewConstMetric(c.units, prometheus.GaugeValue, float64(w.Units))
	ch <- prometheus.MustNewConstMetric(c.seconds, prometheus.GaugeValue, w.AudioSeconds)
	ch <- prometheus.MustNewConstMetric(c.expired, prometheus.CounterValue, float64(w.ExpiredUnfunded))
}
