package clock_test

import (
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
)

func TestFixedNeverSleeps(t *testing.T) {
	t.Parallel()
	at := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	var c clock.Clock = clock.Fixed{T: at}
	if got := c.Now(); !got.Equal(at) {
		t.Fatalf("Now: got %v, want %v", got, at)
	}
	select {
	case got := <-c.After(time.Hour):
		if !got.Equal(at) {
			t.Fatalf("After: got %v, want %v", got, at)
		}
	default:
		t.Fatal("After on a fixed clock must already have fired")
	}
}

func TestSystemAdvances(t *testing.T) {
	t.Parallel()
	var c clock.Clock = clock.System{}
	first := c.Now()
	<-c.After(time.Millisecond)
	if !c.Now().After(first) {
		t.Fatal("the system clock did not advance across After")
	}
}
