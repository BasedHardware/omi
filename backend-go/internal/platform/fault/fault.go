// Package fault provides seeded, replayable fault schedules for local tests.
package fault

import (
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
	"slices"
	"sync"
)

// Point names a boundary where a test may inject a crash or lost response.
type Point string

// Named injection points used by queue operations and guarded ports.
const (
	QueueClaim            Point = "queue.claim"
	QueueClaimAfterCommit Point = "queue.claim.after_commit"
	LeaseRenewal          Point = "queue.lease_renewal"
	LeaseRenewalAfter     Point = "queue.lease_renewal.after_write"
	QueueSettle           Point = "queue.settle"
	QueueSettleAfter      Point = "queue.settle.after_write"
	PostgresCommit        Point = "postgres.commit"
	ResumeClaimStop       Point = "workers.resume.after_claim"
)

// PortBefore names the point immediately before a guarded port operation.
func PortBefore(name string) Point { return Point("port." + name + ".before") }

// PortAfter names the point immediately after a guarded port operation.
func PortAfter(name string) Point { return Point("port." + name + ".after") }

// ErrInjected marks a point reached by a saved fault schedule.
var ErrInjected = errors.New("fault schedule injected")

// Schedule is reproducible input for a fault run. The seed determines the
// order in which the listed points are armed; Points name the crash seams.
type Schedule struct {
	Seed   uint64  `json:"seed"`
	Points []Point `json:"points"`
}

// Injector consumes the schedule once, in its seed-derived order. A point not
// currently reached stays armed for a later call.
type Injector struct {
	mu       sync.Mutex
	schedule Schedule
	ordered  []Point
	next     int
	history  []Point
}

// New validates and copies a schedule into a concurrency-safe injector.
func New(schedule Schedule) (*Injector, error) {
	if len(schedule.Points) == 0 {
		return nil, fmt.Errorf("fault schedule has no points")
	}
	for i, point := range schedule.Points {
		if point == "" {
			return nil, fmt.Errorf("fault schedule point %d is empty", i)
		}
	}
	ordered := slices.Clone(schedule.Points)
	shuffle(schedule.Seed, ordered)
	schedule.Points = slices.Clone(schedule.Points)
	return &Injector{schedule: schedule, ordered: ordered}, nil
}

// Inject returns an injected error when point is the next armed schedule point.
func (i *Injector) Inject(point Point) error {
	i.mu.Lock()
	defer i.mu.Unlock()
	if i.next >= len(i.ordered) || i.ordered[i.next] != point {
		return nil
	}
	i.next++
	i.history = append(i.history, point)
	return &InjectionError{Seed: i.schedule.Seed, Point: point}
}

// Remaining reports how many scheduled points have not fired.
func (i *Injector) Remaining() int {
	i.mu.Lock()
	defer i.mu.Unlock()
	return len(i.ordered) - i.next
}

// History returns the points injected so far.
func (i *Injector) History() []Point {
	i.mu.Lock()
	defer i.mu.Unlock()
	return slices.Clone(i.history)
}

// Schedule returns a defensive copy of the source schedule.
func (i *Injector) Schedule() Schedule {
	i.mu.Lock()
	defer i.mu.Unlock()
	s := i.schedule
	s.Points = slices.Clone(s.Points)
	return s
}

// InjectionError identifies the seed and point that fired.
type InjectionError struct {
	Seed  uint64
	Point Point
}

func (e *InjectionError) Error() string {
	return fmt.Sprintf("%v: seed=%d point=%s", ErrInjected, e.Seed, e.Point)
}

func (e *InjectionError) Unwrap() error { return ErrInjected }

func shuffle(seed uint64, points []Point) {
	for i := len(points) - 1; i > 0; i-- {
		var input [16]byte
		binary.LittleEndian.PutUint64(input[:8], seed)
		binary.LittleEndian.PutUint64(input[8:], uint64(i))
		order := sha256.Sum256(input[:])
		j := binary.LittleEndian.Uint64(order[:8]) % uint64(i+1)
		points[i], points[j] = points[j], points[i]
	}
}
