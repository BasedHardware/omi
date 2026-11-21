package rules

import "strings"

// NeedsNotes skips already completed structure except for a minimum this job owns.
func NeedsNotes(status Status, pendingMinimum bool) bool {
	return status != Completed || pendingMinimum
}

// HasSummary implements the visible output rule for overview and section bodies.
func HasSummary(overview string, sections []string) bool {
	if strings.TrimSpace(overview) != "" {
		return true
	}
	for _, section := range sections {
		if strings.TrimSpace(section) != "" {
			return true
		}
	}
	return false
}

// Effects describes the ordinary intelligence and external delivery decisions.
type Effects uint8

// Derived effects dispositions.
const (
	SuppressEffects Effects = iota
	DeferEffects
	EagerEffects
)

// PlanEffects selects whether to act now, defer, or suppress derived effects.
func PlanEffects(trigger Trigger, recordingLayer, terminalNoDerived, lazy bool) Effects {
	switch {
	case trigger == SilentBackfill || trigger == HistoricalOpen || recordingLayer || terminalNoDerived:
		return SuppressEffects
	case lazy:
		return DeferEffects
	default:
		return EagerEffects
	}
}
