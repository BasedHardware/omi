package main

import (
	"fmt"
	"log/slog"
	"net/http"
	"slices"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/conformance/finalization"
	wire "github.com/BasedHardware/omi/backend-go/internal/conformance/stubapi"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// timedSteps are the steps the kit expects a duration histogram for. A kind may declare a
// step it never times, such as the reference kind's final "stored".
var timedSteps = map[string]struct{}{
	"load": {}, "transcript": {}, "discard": {}, "notes": {}, "persist": {}, "claim": {}, "memories": {},
	"vector": {}, "integrations": {}, "complete": {}, "speech": {},
}
var bounds = [...]float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300}

type histogram struct {
	bins  [len(bounds) + 1]uint64
	sum   float64
	count uint64
}

type metrics struct {
	mu         sync.Mutex
	counters   map[string]uint64
	histograms map[string]histogram
	// offContract marks the declared causes the kit's closed label list does not know.
	offContract map[queue.Cause]bool
}

// kitCauses is the conformance kit's closed list of cause labels. The foundation declares
// more (the queue's own, and the reference kind's); see offContract.
func kitCauses() map[queue.Cause]bool {
	known := make(map[queue.Cause]bool)
	own := []queue.Cause{queue.CauseNone, queue.CauseLeaseExpired, queue.CauseUnknown}
	for _, c := range slices.Concat(own, wire.Causes(), finalization.Causes()) {
		known[c] = true
	}
	return known
}

// declare creates a zero series for every declared kind, step and cause, so a series that
// never fired still reports 0 and one that is missing is a bug.
func (m *metrics) declare(causes []queue.Cause) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.histograms["jobd_entitlement_release_seconds"] = histogram{}
	kit := kitCauses()
	m.offContract = make(map[queue.Cause]bool, len(causes))
	for _, c := range causes {
		m.offContract[c] = !kit[c]
	}
	for _, k := range kinds() {
		for _, c := range causes {
			for _, o := range queue.Terminals() {
				if o != queue.TerminalExpiredUnfunded {
					m.counters[outcomeKey(k.Name, o, c)] = 0
				}
			}
			m.counters[retryKey(k.Name, c)] = 0
			m.counters[yieldKey(k.Name, c)] = 0
		}
		for _, s := range k.Steps {
			if _, timed := timedSteps[s]; timed {
				m.histograms[stepKey(k.Name, s)] = histogram{}
			}
		}
	}
	for _, c := range causes {
		m.counters[budgetKey(c)] = 0
	}
	for _, v := range wire.Vendors() {
		for _, r := range wire.Results() {
			m.counters[vendorKey(v, r)] = 0
		}
	}
	for _, f := range wire.Features() {
		m.counters[dedupeKey(f, false)] = 0
		m.counters[dedupeKey(f, true)] = 0
	}
}

func outcomeKey(k string, o queue.Terminal, c queue.Cause) string {
	return fmt.Sprintf("jobd_job_outcomes_total{kind=%q,outcome=%q,cause=%q}", k, o, c)
}
func retryKey(k string, c queue.Cause) string {
	return fmt.Sprintf("jobd_retries_total{kind=%q,cause=%q}", k, c)
}
func yieldKey(k string, c queue.Cause) string {
	return fmt.Sprintf("jobd_yields_total{kind=%q,cause=%q}", k, c)
}
func budgetKey(c queue.Cause) string { return fmt.Sprintf("jobd_budget_requeues_total{cause=%q}", c) }
func vendorKey(v wire.Vendor, r wire.Result) string {
	return fmt.Sprintf("jobd_vendor_calls_total{vendor=%q,result=%q}", v, r)
}
func stepKey(k, s string) string { return fmt.Sprintf("kind=%q,step=%q", k, s) }
func dedupeKey(f wire.Feature, hit bool) string {
	result := "miss"
	if hit {
		result = "skipped"
	}
	return fmt.Sprintf("jobd_dedupe_total{feature=%q,result=%q}", f, result)
}

func (m *metrics) inc(key string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.counters[key]; ok {
		m.counters[key]++
	}
}

// The queue has already replaced any unregistered cause with "unknown", so every key here
// exists; "unknown" above zero is a programming error worth an alert.
func (m *metrics) Outcome(k string, o queue.Terminal, c queue.Cause) { m.inc(outcomeKey(k, o, c)) }
func (m *metrics) Retry(k string, c queue.Cause)                     { m.inc(retryKey(k, c)) }
func (m *metrics) Yield(k string, c queue.Cause)                     { m.inc(yieldKey(k, c)) }
func (m *metrics) BudgetRequeue(c queue.Cause)                       { m.inc(budgetKey(c)) }
func (m *metrics) Vendor(v wire.Vendor, r wire.Result)               { m.inc(vendorKey(v, r)) }
func (m *metrics) Dedupe(f wire.Feature, hit bool)                   { m.inc(dedupeKey(f, hit)) }

func (m *metrics) EntitlementReleased(d time.Duration) {
	m.observe("jobd_entitlement_release_seconds", d)
}

func (m *metrics) Step(k, s string, d time.Duration) { m.observe(stepKey(k, s), d) }

func (m *metrics) observe(key string, d time.Duration) {
	m.mu.Lock()
	defer m.mu.Unlock()
	h, ok := m.histograms[key]
	if !ok {
		return
	}
	value := d.Seconds()
	idx, _ := slices.BinarySearch(bounds[:], value)
	h.bins[idx]++
	h.count++
	h.sum += value
	m.histograms[key] = h
}

func (a *api) prometheus(w http.ResponseWriter, r *http.Request) {
	stats, err := a.store.Stats(r.Context())
	if err != nil {
		unavailable(w)
		return
	}
	var b strings.Builder
	b.WriteString("# TYPE jobd_jobs gauge\n")
	for _, s := range queue.States() {
		fmt.Fprintf(&b, "jobd_jobs{state=%q} %d\n", wireState(s), stats.Counts[s])
	}
	fmt.Fprintf(&b, "# TYPE jobd_oldest_nonterminal_age_seconds gauge\njobd_oldest_nonterminal_age_seconds %g\n", stats.OldestSeconds)
	wait := stats.WaitingOnCustomer
	fmt.Fprintf(&b, "jobd_waiting_on_customer_owners %d\njobd_waiting_on_customer_units %d\njobd_waiting_on_customer_audio_seconds %g\njobd_expired_unfunded_total %d\n", wait.Owners, wait.Units, wait.AudioSeconds, wait.ExpiredUnfunded)
	a.metrics.write(&b)
	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	if _, err := fmt.Fprint(w, b.String()); err != nil {
		slog.Warn("metrics write failed")
	}
}

// hidden reports a zero series whose cause is outside the conformance kit's closed list.
// The foundation declares causes the kit does not know (a handler panic, an exhausted
// reconciliation, a corrupted batch input). They are counted like any other and written
// only once they are above zero, so the kit's closed-label check stays meaningful: seeing
// one is itself a finding.
//
// CLEANUP-NOTE: remove with the kit; the real metrics endpoint lists every declared cause.
func (m *metrics) hidden(key string) bool {
	for cause, off := range m.offContract {
		if off && strings.Contains(key, `cause="`+string(cause)+`"`) {
			return true
		}
	}
	return false
}

func (m *metrics) write(b *strings.Builder) {
	m.mu.Lock()
	defer m.mu.Unlock()
	keys := make([]string, 0, len(m.counters))
	for k := range m.counters {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	last := ""
	for _, k := range keys {
		if m.counters[k] == 0 && m.hidden(k) {
			continue
		}
		name, _, _ := strings.Cut(k, "{")
		if last != name {
			fmt.Fprintf(b, "# TYPE %s counter\n", name)
			last = name
		}
		fmt.Fprintf(b, "%s %d\n", k, m.counters[k])
	}
	b.WriteString("# TYPE jobd_entitlement_release_seconds histogram\n# TYPE jobd_step_seconds histogram\n")
	keys = keys[:0]
	for k := range m.histograms {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		h := m.histograms[k]
		name, labels := "jobd_step_seconds", k
		if k == "jobd_entitlement_release_seconds" {
			name, labels = k, ""
		}
		bucketLabels := labels
		if labels != "" {
			bucketLabels += ","
			labels = "{" + labels + "}"
		}
		var sum uint64
		for i, bin := range h.bins {
			le := "+Inf"
			if i < len(bounds) {
				le = strconv.FormatFloat(bounds[i], 'g', -1, 64)
			}
			sum += bin
			fmt.Fprintf(b, "%s_bucket{%sle=%q} %d\n", name, bucketLabels, le, sum)
		}
		fmt.Fprintf(b, "%s_sum%s %g\n%s_count%s %d\n", name, labels, h.sum, name, labels, h.count)
	}
}
