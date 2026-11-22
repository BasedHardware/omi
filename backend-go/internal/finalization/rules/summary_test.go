package rules

import "testing"

func TestF27OnlyEligibleServerMinimumsKeepDebt(t *testing.T) {
	t.Parallel()
	baseline := SummaryDebt{Complete: true, ServerMinimum: true}
	if !CanRepairSummary(baseline) {
		t.Fatal("title-only server minimum lost debt")
	}
	for name, block := range map[string]func(*SummaryDebt){
		"manual":     func(d *SummaryDebt) { d.Manual = true },
		"short":      func(d *SummaryDebt) { d.IntentionalShort = true },
		"historical": func(d *SummaryDebt) { d.Historical = true },
		"discard":    func(d *SummaryDebt) { d.Discarded = true },
		"summary":    func(d *SummaryDebt) { d.HasSummary = true },
		"finalizer":  func(d *SummaryDebt) { d.FinalizerOwns = true },
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			debt := baseline
			block(&debt)
			if CanRepairSummary(debt) {
				t.Fatal("ineligible debt admitted")
			}
		})
	}
}

func TestF28OnlyTwoNewContentRevisionsRearmEmptyOutput(t *testing.T) {
	t.Parallel()
	if RearmSummary(4, 4, 0, true, false) != SummaryKeepBlocked ||
		RearmSummary(4, 5, 0, true, false) != SummaryResetEmpty ||
		RearmSummary(5, 6, 1, true, false) != SummaryResetEmpty ||
		RearmSummary(6, 7, 2, true, false) != SummaryLifetimeBlocked ||
		RearmSummary(4, 5, 0, true, true) != SummaryKeepBlocked {
		t.Fatal("summary empty-output lifetime cap changed")
	}
}
