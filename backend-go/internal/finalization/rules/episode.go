package rules

import "time"

// EpisodeTrigger recognizes the capture and sync entry points for reconciliation.
func EpisodeTrigger(trigger Trigger) bool {
	switch trigger {
	case CaptureEnd, ClientFinalize, ServerRecovery, SyncUpdate, CaptureGroup:
		return true
	case FirstOpen, BacklogChoice, UserReprocess, Merge, SmartMerge, ScreenEvidence, SilentBackfill, HistoricalOpen:
		return false
	}
	return false
}

// CloseEpisode determines whether the member can end its live occasion.
func CloseEpisode(trigger Trigger, liveMember, occasionMode, isTail, recordedMode, idleDue bool) bool {
	if !EpisodeTrigger(trigger) || !liveMember || trigger == SyncUpdate || trigger == CaptureGroup {
		return false
	}
	return trigger == ClientFinalize || (occasionMode && isTail && (!recordedMode || idleDue))
}

// EpisodeEffects checks post-fanout eligibility independently of closing.
func EpisodeEffects(trigger Trigger, clientSeen, trusted, recordingLayer, unchangedSync, absorbed bool) bool {
	return EpisodeTrigger(trigger) && clientSeen && trusted && !recordingLayer &&
		(trigger != SyncUpdate || !unchangedSync || absorbed)
}

// RetainedSpeech returns new segment IDs in input order and the monotone activity
// clock. Retained segment identity does not depend on saved audio placement.
func RetainedSpeech(consumed map[string]bool, incoming []string, lastActivity, speechAt time.Time) ([]string, time.Time) {
	seen := make(map[string]bool, len(incoming))
	var added []string
	for _, id := range incoming {
		if id != "" && !consumed[id] && !seen[id] {
			added = append(added, id)
			seen[id] = true
		}
	}
	if len(added) > 0 && speechAt.After(lastActivity) {
		lastActivity = speechAt
	}
	return added, lastActivity
}
