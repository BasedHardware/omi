// Package rules contains finalization decisions over snapshots, without I/O.
package rules

import "time"

// Trigger records the immutable reason for processing a revision.
type Trigger string

// Processing reasons recognized by the serving lifecycle.
const (
	CaptureEnd     Trigger = "capture_end"
	ClientFinalize Trigger = "client_finalize"
	SyncUpdate     Trigger = "sync_update"
	FirstOpen      Trigger = "first_open"
	BacklogChoice  Trigger = "backlog_choice"
	UserReprocess  Trigger = "user_reprocess"
	Merge          Trigger = "merge"
	SmartMerge     Trigger = "smart_merge"
	CaptureGroup   Trigger = "capture_group"
	ScreenEvidence Trigger = "screen_evidence"
	ServerRecovery Trigger = "server_recovery"
	SilentBackfill Trigger = "silent_backfill"
	HistoricalOpen Trigger = "historical_open"
)

// Mode controls eager enrichment, created effects and relevance assessment.
type Mode struct {
	RunNow, Reprocess, AssessRelevance bool
}

// ProcessingMode mirrors the lifecycle trigger table.
func ProcessingMode(trigger Trigger) (Mode, bool) {
	switch trigger {
	case CaptureEnd:
		return Mode{AssessRelevance: true}, true
	case ClientFinalize:
		return Mode{RunNow: true, AssessRelevance: true}, true
	case SyncUpdate:
		return Mode{RunNow: true, Reprocess: true, AssessRelevance: true}, true
	case FirstOpen, Merge:
		return Mode{RunNow: true}, true
	case BacklogChoice, UserReprocess, SmartMerge, CaptureGroup, ScreenEvidence, ServerRecovery, SilentBackfill, HistoricalOpen:
		return Mode{RunNow: true, Reprocess: true}, true
	}
	return Mode{}, false
}

// Status is the conversation's stored lifecycle status.
type Status string

// Stored conversation lifecycle statuses.
const (
	InProgress Status = "in_progress"
	Processing Status = "processing"
	Merging    Status = "merging"
	Completed  Status = "completed"
	Failed     Status = "failed"
)

// RecordingLease distinguishes a known expiry from missing evidence.
type RecordingLease uint8

// Recording lease evidence states.
const (
	LeaseUnknown RecordingLease = iota
	LeaseActive
	LeaseExpired
)

// AdmissionFacts are read inside the outbox transaction, including any sidecar
// required to establish content, recording custody or an owner-wide backfill lock.
type AdmissionFacts struct {
	Status                 Status
	ExistingJob            bool
	HasBinding             bool
	Deleted                bool
	Discarded              bool
	OwnerDeleting          bool
	Protected              bool
	Deferred               bool
	LocalPending           bool
	TerminalNoDerived      bool
	HasContent             bool
	RecoverySource         bool
	RecoveryContentBounded bool
	BackfillEligible       bool
	QuietDeadlinePassed    bool
	BackfillOwnerAvailable bool
	LastSpeech             time.Time
	RecordingLease         RecordingLease
}

// AdmissionAction is the sole action permitted by an admission snapshot.
type AdmissionAction uint8

// Allowed outbox transaction decisions.
const (
	Refuse AdmissionAction = iota
	UseBound
	BindNext
)

// Admission decides whether to reuse the bound intent or bind a revision. The store
// checks for an already existing deterministic id before creating the new intent.
func Admission(trigger Trigger, cutoff time.Time, requireExpiredLease bool, facts AdmissionFacts) AdmissionAction {
	if facts.Deleted || facts.OwnerDeleting {
		return Refuse
	}
	switch trigger {
	case ServerRecovery:
		if recoveryAllowed(cutoff, requireExpiredLease, facts) {
			return BindNext
		}
	case SilentBackfill:
		if facts.BackfillEligible && facts.BackfillOwnerAvailable && recoveryAllowed(cutoff, requireExpiredLease, facts) {
			return BindNext
		}
	case CaptureEnd, ClientFinalize:
		switch {
		case facts.Status == Completed || facts.Status == Failed || facts.Discarded || facts.Deferred || facts.Protected || !facts.HasContent:
			return Refuse
		case facts.ExistingJob:
			return UseBound
		case facts.Status == InProgress:
			return BindNext
		}
	case SyncUpdate, FirstOpen, BacklogChoice, UserReprocess, Merge, SmartMerge, CaptureGroup, ScreenEvidence, HistoricalOpen:
		// These entry points use a separate processing protocol.
	}
	return Refuse
}

func recoveryAllowed(cutoff time.Time, requireExpiredLease bool, facts AdmissionFacts) bool {
	return facts.Status == InProgress && !facts.Discarded && !facts.Deferred && !facts.LocalPending &&
		!facts.TerminalNoDerived && !facts.Protected && !facts.HasBinding && facts.RecoverySource &&
		facts.HasContent && facts.RecoveryContentBounded && facts.QuietDeadlinePassed && !cutoff.IsZero() &&
		!facts.LastSpeech.IsZero() && !facts.LastSpeech.After(cutoff) &&
		facts.RecordingLease != LeaseActive && (!requireExpiredLease || facts.RecordingLease == LeaseExpired)
}
