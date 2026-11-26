package finalizationdocs

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

const summaryCursorID = "summary_debt_repair_v1"

const (
	summaryInterval         = 2 * time.Minute
	summaryScanTime         = 90 * time.Second
	summaryScanLimit        = 100
	summaryAdmissionLimit   = 8
	summaryOwnerLimit       = 3
	summaryNearExpiryWindow = 10 * time.Minute
)

var errSummaryScan = errors.New("finalization: summary scan unavailable")

// SummaryScan hands due obligations to the existing enrichment outbox. It
// shares the cursor and scan lease with the Python scheduler during cutover.
type SummaryScan struct {
	Docs   *docstore.Store
	Family *finalization.Service
	Clock  clock.Clock
	MaxAge time.Duration
}

// SummaryScanCounts reports counts without owner IDs or provider details.
type SummaryScanCounts struct {
	Scanned, Attempted, Admitted, Errors int
}

type summaryWalk struct {
	counts SummaryScanCounts
	owners map[string]int
	now    time.Time
}

type summaryPhase string

const (
	nearExpiry summaryPhase = "near_expiry"
	newest     summaryPhase = "newest"
)

// Tick claims the scan, advances its durable cursor, and leaves task creation
// to the serving enrichment dispatcher that already owns these outbox rows.
func (s SummaryScan) Tick(ctx context.Context) (SummaryScanCounts, error) {
	if s.Docs == nil || s.Family == nil || s.Family.Queue == nil || s.Family.Summaries == nil || s.Clock == nil || s.MaxAge < 0 {
		return SummaryScanCounts{}, finalization.ErrInvalid
	}
	scanCtx, cancel := context.WithTimeout(ctx, summaryScanTime)
	defer cancel()
	now := s.Clock.Now().UTC()
	owner, err := newUUID()
	if err != nil {
		return SummaryScanCounts{}, errSummaryScan
	}
	cursor, err := s.claimSummaryScan(scanCtx, owner, now)
	if err != nil || cursor == nil {
		return SummaryScanCounts{}, err
	}
	walk := summaryWalk{now: now, owners: make(map[string]int)}
	progress, scanErr := s.scanSummaryDebt(scanCtx, cursor, &walk)
	finishCtx, finishCancel := context.WithTimeout(ctx, 5*time.Second)
	defer finishCancel()
	finishErr := s.finishSummaryScan(finishCtx, owner, progress)
	return walk.counts, errors.Join(scanErr, finishErr)
}

func (s SummaryScan) claimSummaryScan(ctx context.Context, owner string, now time.Time) (document, error) {
	var cursor document
	err := s.Docs.UpdateMaintenance(ctx, summaryCursorID, func(row map[string]any) map[string]any {
		cursor = nil
		if seconds(row, "lease_until").After(now) || seconds(row, "next_at").After(now) {
			return nil
		}
		cursor = row
		next := unix(now.Add(summaryInterval))
		return document{"owner": owner, "lease_until": next, "next_at": next}
	})
	if err != nil {
		return nil, errSummaryScan
	}
	return cursor, nil
}

func (s SummaryScan) finishSummaryScan(ctx context.Context, owner string, progress document) error {
	err := s.Docs.UpdateMaintenance(ctx, summaryCursorID, func(row map[string]any) map[string]any {
		if field[string](row, "owner") != owner {
			return nil
		}
		next := document{"lease_until": 0, "version": 2, "phases": document{}, "path": nil, "due": nil, "pending": nil}
		if s.MaxAge == 0 {
			if last := field[map[string]any](progress, string(newest)); last != nil {
				next["path"], next["due"] = last["path"], last["due"]
			}
		} else {
			next["phases"] = progress
		}
		return next
	})
	if err != nil {
		return errSummaryScan
	}
	return nil
}

func (s SummaryScan) scanSummaryDebt(ctx context.Context, cursor document, walk *summaryWalk) (document, error) {
	phases := []summaryPhase{newest}
	progress := make(document)
	if s.MaxAge > 0 {
		phases = []summaryPhase{nearExpiry, newest}
		if field[int64](cursor, "version") == 2 {
			for _, phase := range phases {
				progress[string(phase)] = field[map[string]any](field[map[string]any](cursor, "phases"), string(phase))
			}
		}
	} else if cursor["pending"] == nil {
		progress[string(newest)] = document{"path": cursor["path"], "due": cursor["due"]}
	}

	var failure error
	for _, phase := range phases {
		if walk.full() || ctx.Err() != nil {
			break
		}
		previous := field[map[string]any](progress, string(phase))
		next, err := s.scanSummaryPhase(ctx, phase, previous, walk)
		if err != nil {
			walk.counts.Errors++
			failure = err
		}
		progress[string(phase)] = next
	}
	return progress, failure
}

func (w summaryWalk) full() bool {
	return w.counts.Scanned >= summaryScanLimit || w.counts.Attempted >= summaryAdmissionLimit
}

func (s SummaryScan) scanSummaryPhase(ctx context.Context, phase summaryPhase, after document, walk *summaryWalk) (document, error) {
	for !walk.full() && ctx.Err() == nil {
		limit := min(16, summaryScanLimit-walk.counts.Scanned)
		query := s.summaryQuery(phase, after, walk.now)
		query.Limit = limit
		rows, err := s.Docs.ScanGroup(ctx, query)
		if err != nil {
			return after, errSummaryScan
		}
		walk.counts.Scanned += len(rows)
		for _, row := range rows {
			if ctxErr := ctx.Err(); ctxErr != nil {
				return after, ctxErr
			}
			if walk.counts.Attempted >= summaryAdmissionLimit {
				return after, nil
			}
			ref := summaryCandidate(row.Path)
			after = s.cursorFor(phase, row.Path, row.Fields)
			s.admitSummaryCandidate(ctx, row.Fields, ref, walk)
		}
		if len(rows) < limit {
			return document{}, nil
		}
	}
	return after, nil
}

func (s SummaryScan) cursorFor(phase summaryPhase, path string, row document) document {
	cursor := document{"path": path, "due": row["summary_due_at"], "phase": string(phase)}
	if s.MaxAge > 0 {
		cursor["pending"] = row["summary_first_pending_at"]
		cursor["window"] = s.MaxAge.Seconds()
	}
	return cursor
}

func (s SummaryScan) admitSummaryCandidate(ctx context.Context, row document, ref finalization.Ref, walk *summaryWalk) {
	if ref.Owner == "" || field[string](row, "summary_title_provenance") != "server_minimum" || walk.owners[ref.Owner] >= summaryOwnerLimit {
		return
	}
	walk.owners[ref.Owner]++
	walk.counts.Attempted++
	result, err := s.Family.RepairSummary(ctx, ref, s.MaxAge)
	if err != nil {
		walk.counts.Errors++
		return
	}
	if result == rules.SummaryWake {
		walk.counts.Admitted++
	}
}

func summaryCandidate(path string) finalization.Ref {
	parts := strings.Split(path, "/")
	if len(parts) != 4 || parts[0] != "users" || parts[2] != "conversations" {
		return finalization.Ref{}
	}
	return finalization.Ref{Owner: parts[1], ID: parts[3]}
}

func (s SummaryScan) summaryQuery(phase summaryPhase, after document, now time.Time) docstore.GroupScan {
	query := docstore.GroupScan{
		Collection: "conversations",
		Filters:    []docstore.Filter{{Field: "summary_due_at", Operator: "<=", Value: unix(now)}},
		Fields:     []string{"summary_due_at", "summary_first_pending_at", "summary_title_provenance"},
	}
	if s.MaxAge > 0 {
		cutoff := now.Add(-s.MaxAge)
		boundary := cutoff.Add(summaryNearExpiryWindow)
		operator := "<="
		if phase == newest {
			operator = ">"
		}
		query.Filters = append(query.Filters,
			docstore.Filter{Field: "summary_first_pending_at", Operator: ">=", Value: unix(cutoff)},
			docstore.Filter{Field: "summary_first_pending_at", Operator: operator, Value: unix(boundary)})
		query.Orders = append(query.Orders, docstore.ScanOrder{Field: "summary_first_pending_at", Descending: phase == newest})
		if !s.validSummaryCursor(phase, after, cutoff, boundary) {
			after = nil
		}
	}
	query.Orders = append(query.Orders, docstore.ScanOrder{Field: "summary_due_at"})
	if path := field[string](after, "path"); path != "" && !seconds(after, "due").IsZero() {
		if s.MaxAge > 0 {
			query.AfterPath, query.After = path, []any{after["pending"], after["due"]}
		} else if after["pending"] == nil {
			query.AfterPath, query.After = path, []any{after["due"]}
		}
	}
	return query
}

func (s SummaryScan) validSummaryCursor(phase summaryPhase, row document, cutoff, boundary time.Time) bool {
	if field[string](row, "phase") != string(phase) || (row["window"] != s.MaxAge.Seconds() && row["window"] != int64(s.MaxAge.Seconds())) {
		return false
	}
	pending := seconds(row, "pending")
	if phase == nearExpiry {
		return !pending.Before(cutoff) && !pending.After(boundary)
	}
	return pending.After(boundary)
}
