package rules

import "math"

// MergeEvidence identifies the cached question and the eligible pair it described.
type MergeEvidence struct {
	Candidate, Question, ContentDigest string
	DonorRevision, SurvivorRevision    int64
	GapTenths                          *int64
	SpeechGap                          bool
}

// ReuseMergeDecision matches the stored evidence needed by the current
// stage. Same-recording decisions additionally bind the measured gap.
func ReuseMergeDecision(prior, current MergeEvidence, beforeNotes, sameRecording bool) bool {
	if current.Candidate == "" || current.Question == "" || prior.Candidate != current.Candidate || prior.Question != current.Question {
		return false
	}
	if beforeNotes && (prior.ContentDigest != current.ContentDigest || prior.DonorRevision != current.DonorRevision ||
		prior.SurvivorRevision != current.SurvivorRevision) {
		return false
	}
	return !sameRecording || (!prior.SpeechGap && prior.GapTenths != nil && current.GapTenths != nil && *prior.GapTenths == *current.GapTenths)
}

// MergeDecision is the effect allowed after an eligible pair was scored.
type MergeDecision uint8

// Smart-merge actions.
const (
	KeepPair MergeDecision = iota
	ObservePair
	AbsorbPair
)

// ChooseMerge rejects unavailable or out-of-range scores and keeps shadow read-only.
func ChooseMerge(score, threshold float64, eligible, shadow bool) MergeDecision {
	if !eligible || math.IsNaN(score) || math.IsNaN(threshold) || score < 0 || score > 1 {
		return KeepPair
	}
	if shadow {
		return ObservePair
	}
	if score < threshold {
		return KeepPair
	}
	return AbsorbPair
}

// MergePhase identifies the irreversible source-cleanup boundary.
type MergePhase string

// Explicit merge phases used by recovery.
const (
	MergePreparing     MergePhase = "preparing"
	MergeRecovering    MergePhase = "recovering"
	MergeSourceCleanup MergePhase = "source_cleanup"
	MergeRolledBack    MergePhase = "rolled_back"
)

// MergeRecovery is the only permitted action after the current lease is due.
type MergeRecovery uint8

// Recovery actions are closed so an unknown phase cannot release sources.
const (
	MergeRecoveryNone MergeRecovery = iota
	MergeRollback
	MergeResumeCleanup
	MergeManual
)

// RecoverMerge retains the target after sealing and caps cleanup at five claims.
func RecoverMerge(phase MergePhase, attempts int64) MergeRecovery {
	switch phase {
	case MergePreparing, MergeRecovering:
		return MergeRollback
	case MergeSourceCleanup:
		if attempts >= 5 {
			return MergeManual
		}
		return MergeResumeCleanup
	case MergeRolledBack:
		return MergeRecoveryNone
	}
	return MergeRecoveryNone
}
