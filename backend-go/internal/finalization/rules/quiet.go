package rules

import (
	"math"
	"time"
)

// QuietTimeout bounds a disconnect timeout in seconds as stored by Python.
func QuietTimeout(seconds float64) time.Duration {
	if math.IsNaN(seconds) || math.IsInf(seconds, 0) {
		seconds = 120
	}
	return time.Duration(max(1, min(seconds, 14400)) * float64(time.Second))
}

// QuietAction records what to do with a current durable quiet obligation.
type QuietAction uint8

// Quiet wake results. Repair leaves custody to a separate recovery path.
const (
	QuietStale QuietAction = iota
	QuietRetire
	QuietWait
	QuietReady
	QuietRepair
)

// PlanQuietWake decides whether the current check can try recovery and when its
// successor wakes. An unknown lease cannot prove that recording stopped.
func PlanQuietWake(now, deadline, leaseExpiry time.Time, eligible, hasContent bool) (QuietAction, time.Time) {
	if !eligible || deadline.IsZero() {
		return QuietRetire, time.Time{}
	}
	successor := maxQuietTime(now.Add(time.Minute), deadline, leaseExpiry)
	if leaseExpiry.IsZero() || leaseExpiry.After(now) || deadline.After(now) {
		return QuietWait, successor
	}
	if !hasContent {
		return QuietRepair, time.Time{}
	}
	return QuietReady, successor
}

func maxQuietTime(a, b, c time.Time) time.Time {
	if b.After(a) {
		a = b
	}
	if c.After(a) {
		a = c
	}
	return a
}
