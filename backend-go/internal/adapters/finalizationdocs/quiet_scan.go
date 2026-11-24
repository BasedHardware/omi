package finalizationdocs

import (
	"context"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

const quietScanLimit = 50

// QuietScan delivers due quiet checks through the workerd-owned finalization
// family. Its cursor rotates past blocked owners. A single caller drives Tick.
type QuietScan struct {
	Docs   *docstore.Store
	Family *finalization.Service
	Clock  clock.Clock
	path   string
	due    any
	cutoff time.Time
}

// Tick walks a bounded page and returns the number of failed deliveries.
// Durable wake generations fence overlapping ticks and late Cloud Tasks.
func (s *QuietScan) Tick(ctx context.Context) (int, error) {
	bounded, cancel := context.WithTimeout(ctx, 25*time.Second)
	defer cancel()
	if s.cutoff.IsZero() {
		s.cutoff = s.Clock.Now().UTC()
	}
	spec := docstore.GroupScan{
		Collection: jobs, Limit: quietScanLimit,
		Filters: []docstore.Filter{{Field: "reconcile_after_at", Operator: "<=", Value: s.cutoff}},
		Orders:  []docstore.ScanOrder{{Field: "reconcile_after_at"}},
		Fields:  []string{"reconcile_after_at", "dispatch_generation", "due_at", "conversation_id", "uid", "kind", "status"},
	}
	if s.path != "" {
		spec.After, spec.AfterPath = []any{s.due}, s.path
	}
	rows, err := s.Docs.ScanCollection(bounded, spec)
	if err != nil {
		return 0, err
	}
	failed := 0
	for _, row := range rows {
		if ctxErr := bounded.Err(); ctxErr != nil {
			return failed, ctxErr
		}
		s.path, s.due = row.Path, row.Fields["reconcile_after_at"]
		if check, ok := toQuietCheck(row); ok {
			if _, _, wakeErr := s.Family.WakeQuiet(bounded, check, true); wakeErr != nil {
				failed++
			}
		}
	}
	if len(rows) < quietScanLimit {
		s.path, s.due, s.cutoff = "", nil, time.Time{}
	}
	return failed, nil
}

func toQuietCheck(row docstore.ScanRow) (finalization.QuietCheck, bool) {
	fields := row.Fields
	check := finalization.QuietCheck{
		Ref:        finalization.Ref{Owner: field[string](fields, "uid"), ID: field[string](fields, "conversation_id")},
		Generation: field[int64](fields, "dispatch_generation"),
		Due:        field[time.Time](fields, "due_at"),
	}
	return check, currentQuiet(fields, check.Generation) && field[string](fields, "kind") == quietKind &&
		check.Ref.Owner != "" && check.Ref.ID != "" && !check.Due.IsZero() &&
		row.Path == jobs+"/"+finalization.QuietID(check.Ref)
}
