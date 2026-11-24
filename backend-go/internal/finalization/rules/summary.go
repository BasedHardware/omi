package rules

import "time"

// SummaryDebt is the authoritative conversation's eligibility for background repair.
type SummaryDebt struct {
	Complete, Deleted, Discarded, LocalOnly, Protected, Manual, Historical, IntentionalShort bool
	HasSummary, EmptyBlocked, ServerMinimum, FinalizerOwns                                   bool
}

// CanRepairSummary applies the lifecycle and provenance gate before the outbox
// may be read or changed.
func CanRepairSummary(debt SummaryDebt) bool {
	return debt.Complete && debt.ServerMinimum && !debt.Deleted && !debt.Discarded && !debt.LocalOnly &&
		!debt.Protected && !debt.Manual && !debt.Historical && !debt.IntentionalShort &&
		!debt.HasSummary && !debt.EmptyBlocked && !debt.FinalizerOwns
}

// SummaryAction selects whether to leave, block, park, or schedule one debt.
type SummaryAction uint8

// Summary repair outcomes.
const (
	SummarySkip SummaryAction = iota
	SummaryBlockBYOK
	SummaryPark
	SummaryWake
)

// SummaryRepair chooses any mutation after comparing the due row and existing outbox.
func SummaryRepair(now, due, pending, created, lease time.Time, maxAge time.Duration, eligible, byok, seen, parked bool) SummaryAction {
	if !eligible || due.IsZero() || due.After(now) {
		return SummarySkip
	}
	if byok {
		return SummaryBlockBYOK
	}
	if seen || parked || lease.After(now) {
		return SummarySkip
	}
	if maxAge > 0 {
		cutoff := now.Add(-maxAge)
		if (!pending.IsZero() && pending.Before(cutoff)) || (!created.IsZero() && created.Before(cutoff)) {
			return SummaryPark
		}
	}
	return SummaryWake
}

// SummaryRearm is the change to exhausted debt a newer content writer may make.
type SummaryRearm uint8

// Empty-output revision transitions.
const (
	SummaryKeepBlocked SummaryRearm = iota
	SummaryResetEmpty
	SummaryLifetimeBlocked
)

// RearmSummary limits the number of fresh empty-output budgets to two.
func RearmSummary(before, after int64, rearms int64, exhausted, hasSummary bool) SummaryRearm {
	if after <= before || !exhausted || hasSummary {
		return SummaryKeepBlocked
	}
	if rearms >= 2 {
		return SummaryLifetimeBlocked
	}
	return SummaryResetEmpty
}
