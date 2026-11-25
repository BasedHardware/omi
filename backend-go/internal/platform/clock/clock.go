// Package clock is the only place, besides a binary's main package, that reads the wall clock.
//
// Code that needs the time takes a Clock. Code that only decides takes a time.Time value.
// That keeps every time-dependent rule testable without sleeping, and makes a function's
// dependence on time visible in its signature.
package clock

import "time"

// Clock reads the current time and waits.
type Clock interface {
	// Now returns the current time.
	Now() time.Time
	// After returns a channel that receives once d has elapsed.
	After(d time.Duration) <-chan time.Time
}

// System is the wall clock.
type System struct{}

// Now returns the wall-clock time.
func (System) Now() time.Time { return time.Now() }

// After waits on the wall clock.
func (System) After(d time.Duration) <-chan time.Time { return time.After(d) }

// Fixed is a clock for tests: Now returns T, and After fires immediately.
type Fixed struct {
	T time.Time
}

// Now returns the fixed time.
func (f Fixed) Now() time.Time { return f.T }

// After returns a channel that has already fired, so tests never sleep.
func (f Fixed) After(time.Duration) <-chan time.Time {
	ch := make(chan time.Time, 1)
	ch <- f.T
	return ch
}
