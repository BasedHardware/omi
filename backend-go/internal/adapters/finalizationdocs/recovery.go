package finalizationdocs

import (
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

func prepareRecovery(tx *docstore.Tx, req finalization.AdmissionRequest, row document, now time.Time, facts *rules.AdmissionFacts) (quietRows, bool, error) {
	var quiet quietRows
	var err error
	if req.QuietGeneration > 0 {
		quiet, err = getQuietRows(tx, req.Ref)
		if err != nil || field[string](quiet.job, "status") != quietWaiting ||
			field[int64](quiet.job, "dispatch_generation") != req.QuietGeneration {
			return quietRows{}, false, err
		}
	}
	expiry, err := recordingExpiry(tx, req.Ref, row)
	if err != nil {
		return quietRows{}, false, err
	}
	switch {
	case expiry.IsZero():
		facts.RecordingLease = rules.LeaseUnknown
	case expiry.After(now):
		facts.RecordingLease = rules.LeaseActive
	default:
		facts.RecordingLease = rules.LeaseExpired
	}
	deadline := quietDeadline(row, rules.QuietTimeout(quietSeconds(row, "listen_quiet_timeout_seconds")))
	facts.QuietDeadlinePassed = !deadline.IsZero() && !deadline.After(now)
	facts.LastSpeech = speechTime(row)
	facts.RecoverySource = quietEligible(row)
	facts.RecoveryContentBounded = boundedAudio(row)
	facts.LocalPending = field[string](row, "processing_state") == "local_pending"
	facts.TerminalNoDerived = field[bool](row, "terminal_no_derived_effects")
	if !producerEnd(row, now) && hasProtectedStructure(row) {
		facts.Protected = true
	}
	return quiet, true, nil
}

func boundedAudio(row document) bool {
	if row["audio_files"] == nil {
		return true
	}
	files, ok := row["audio_files"].([]any)
	if !ok || len(files) > 256 {
		return false
	}
	for _, raw := range files {
		entry, valid := raw.(map[string]any)
		if !valid || strings.TrimSpace(field[string](entry, "id")) == "" {
			return false
		}
	}
	return true
}

func hasProtectedStructure(row document) bool {
	structured := field[map[string]any](row, "structured")
	title := strings.TrimSpace(field[string](structured, "title"))
	// Only known placeholder text is safe to replace during unattended recovery.
	if title == "Discussion notes" || strings.EqualFold(strings.TrimRight(title, ".…"), "transcribing") {
		title = ""
	}
	return title != "" || strings.TrimSpace(field[string](row, "user_title")) != "" ||
		strings.TrimSpace(field[string](structured, "overview")) != "" || strings.TrimSpace(field[string](structured, "gist")) != "" ||
		len(field[[]any](structured, "sections")) > 0 || len(field[[]any](structured, "action_items")) > 0 || len(field[[]any](structured, "events")) > 0
}
