package fault

import (
	"errors"
	"slices"
	"testing"
)

func TestScheduleReplaysTheSameSeededPoints(t *testing.T) {
	t.Parallel()
	schedule := Schedule{Seed: 3173, Points: []Point{"queue.claim", "port.documents.load.before", "queue.settle"}}
	first := replayOrder(t, schedule)
	second := replayOrder(t, schedule)
	if !slices.Equal(first, second) {
		t.Fatalf("same seed changed injected order: %v then %v", first, second)
	}
}

func TestInjectionCarriesSeedAndPoint(t *testing.T) {
	t.Parallel()
	injector, err := New(Schedule{Seed: 44, Points: []Point{QueueClaimAfterCommit}})
	if err != nil {
		t.Fatal(err)
	}
	injectErr := injector.Inject(QueueClaim)
	if injectErr != nil {
		t.Fatalf("unlisted point injected: %v", injectErr)
	}
	err = injector.Inject(QueueClaimAfterCommit)
	var injected *InjectionError
	if !errors.Is(err, ErrInjected) || !errors.As(err, &injected) || injected.Seed != 44 || injected.Point != QueueClaimAfterCommit {
		t.Fatalf("injection = %#v, want seed 44 at %s", err, QueueClaimAfterCommit)
	}
	if injector.Remaining() != 0 || !slices.Equal(injector.History(), []Point{QueueClaimAfterCommit}) {
		t.Fatalf("schedule state: remaining=%d history=%v", injector.Remaining(), injector.History())
	}
}

func replayOrder(t *testing.T, schedule Schedule) []Point {
	t.Helper()
	injector, err := New(schedule)
	if err != nil {
		t.Fatal(err)
	}
	for injector.Remaining() > 0 {
		progress := false
		for _, point := range schedule.Points {
			injectErr := injector.Inject(point)
			if errors.Is(injectErr, ErrInjected) {
				progress = true
			} else if injectErr != nil {
				t.Fatal(injectErr)
			}
		}
		if !progress {
			t.Fatal("schedule stopped making progress")
		}
	}
	return injector.History()
}
