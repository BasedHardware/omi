package queue

import (
	"fmt"
	"slices"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
)

const unknownLabel = "unknown"

// registry is the declared vocabulary of every kind: what may be enqueued, which steps and
// causes are real, and which jobs this binary can run. It is built once at Open and never
// changes, so it is safe to read from any goroutine.
type registry struct {
	kinds  map[string]declared
	causes map[Cause]struct{}
}

type declared struct {
	paidProcessing bool
	formats        []int
	steps          []string
}

func newRegistry(cfg Config, kinds []Kind) (registry, error) {
	r := registry{kinds: make(map[string]declared, len(kinds)), causes: make(map[Cause]struct{})}
	own := []Cause{CauseAllowanceExhausted, CauseNone, CauseLeaseExpired, CauseHandlerPanic, CauseReconcileExhausted, CauseUnknown, cfg.GateAbandoned}
	for _, c := range own {
		r.causes[c] = struct{}{}
	}
	for _, k := range kinds {
		if err := validKind(k); err != nil {
			return registry{}, err
		}
		if _, dup := r.kinds[k.Name]; dup {
			return registry{}, fmt.Errorf("%w: kind %q is declared twice", ErrConfig, k.Name)
		}
		r.kinds[k.Name] = declared{paidProcessing: k.PaidProcessing, formats: slices.Clone(k.Formats), steps: slices.Clone(k.Steps)}
		for _, c := range k.Causes {
			r.causes[c] = struct{}{}
		}
	}
	return r, nil
}

func validKind(k Kind) error {
	switch {
	case k.Name == "" || k.Name == unknownLabel:
		return fmt.Errorf("%w: a kind needs a name other than %q", ErrConfig, unknownLabel)
	case len(k.Formats) == 0 || slices.Min(k.Formats) < 1:
		return fmt.Errorf("%w: kind %q must declare its formats, each 1 or more", ErrConfig, k.Name)
	case len(k.Steps) == 0 || slices.Contains(k.Steps, "") || slices.Contains(k.Steps, unknownLabel):
		return fmt.Errorf("%w: kind %q must declare its steps", ErrConfig, k.Name)
	case slices.Contains(k.Causes, ""):
		return fmt.Errorf("%w: kind %q declares an empty cause", ErrConfig, k.Name)
	}
	return nil
}

// known returns c if it is declared, otherwise CauseUnknown.
func (r registry) known(c Cause) Cause {
	if _, ok := r.causes[c]; ok {
		return c
	}
	return CauseUnknown
}

func (r registry) hasStep(kind, step string) bool {
	return slices.Contains(r.kinds[kind].steps, step)
}

// stepLabel returns step when the kind declares it, so a metric label is always from a
// closed set.
func (r registry) stepLabel(kind, step string) string {
	if r.hasStep(kind, step) {
		return step
	}
	return unknownLabel
}

func (r registry) runs(kind string, format int) bool {
	return slices.Contains(r.kinds[kind].formats, format)
}

// supported is the set of (kind, format) pairs a claim may select, as two parallel arrays
// for one SQL parameter each.
type supported struct {
	kinds   []string
	formats []int32
}

// pairs lists the declared formats of the named kinds.
func (r registry) pairs(names []string) supported {
	var out supported
	for _, name := range names {
		for _, format := range r.kinds[name].formats {
			out.kinds = append(out.kinds, name)
			out.formats = append(out.formats, pg.Int32(format))
		}
	}
	return out
}

func (r registry) names() []string {
	names := make([]string, 0, len(r.kinds))
	for name := range r.kinds {
		names = append(names, name)
	}
	slices.Sort(names)
	return names
}
