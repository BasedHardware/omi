package finalizationdocs

import (
	"context"
	"math"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	quietKind    = "listen_quiet_check"
	quietWaiting = "waiting_quiet"
	quietDone    = "quiet_done"
)

type quietRows struct {
	jobPath, conversationPath docstore.Ref
	job, row                  document
	written                   time.Time
}

func getQuietRows(tx *docstore.Tx, ref finalization.Ref) (quietRows, error) {
	jobPath, err := docstore.Doc(jobs, finalization.QuietID(ref))
	if err != nil {
		return quietRows{}, err
	}
	path, err := conversationRef(ref)
	if err != nil {
		return quietRows{}, err
	}
	rows := quietRows{jobPath: jobPath, conversationPath: path}
	if _, jobErr := tx.Get(jobPath, &rows.job); jobErr != nil {
		return quietRows{}, jobErr
	}
	if rows.job != nil && (field[string](rows.job, "kind") != quietKind || field[string](rows.job, "uid") != ref.Owner ||
		field[string](rows.job, "conversation_id") != ref.ID) {
		return quietRows{}, finalization.ErrInvalid
	}
	rows.written, err = tx.GetVersion(path, &rows.row)
	return rows, err
}

// ArmQuiet preserves an earlier wake, and key evidence never moves backward.
func (s Store) ArmQuiet(ctx context.Context, a queue.Admitting, ref finalization.Ref, timeout float64, requiresBYOK bool) (finalization.QuietCheck, error) {
	now := s.Clock.Now().UTC()
	var check finalization.QuietCheck
	err := s.Docs.Fenced(ctx, a, ref.Owner, func(tx *docstore.Tx) error {
		var armErr error
		check, armErr = armQuiet(tx, ref, now, rules.QuietTimeout(timeout), requiresBYOK)
		return armErr
	})
	return check, classify(err)
}

func armQuiet(tx *docstore.Tx, ref finalization.Ref, now time.Time, timeout time.Duration, requiresBYOK bool) (finalization.QuietCheck, error) {
	rows, err := getQuietRows(tx, ref)
	if err != nil {
		return finalization.QuietCheck{}, err
	}
	row, job := rows.row, rows.job
	deadline := quietDeadline(row, timeout)
	if !quietEligible(row) || deadline.IsZero() {
		return finalization.QuietCheck{}, retireQuiet(tx, rows.jobPath, job, now, "")
	}
	due := deadline
	if due.Before(now) {
		due = now
	}
	generation := field[int64](job, "dispatch_generation")
	if existing := field[time.Time](job, "due_at"); field[string](job, "status") == quietWaiting && !existing.IsZero() && !existing.After(due) {
		due = existing
	} else {
		if generation < 0 || generation == math.MaxInt64 {
			return finalization.QuietCheck{}, finalization.ErrInvalid
		}
		generation++
	}
	required := requiresBYOK || field[bool](row, "listen_finalization_requires_byok")
	if err := tx.Update(rows.conversationPath, document{"listen_quiet_timeout_seconds": timeout.Seconds(), "listen_finalization_requires_byok": required}); err != nil {
		return finalization.QuietCheck{}, err
	}
	created := field[time.Time](job, "created_at")
	if created.IsZero() {
		created = now
	}
	next := document{
		"kind": quietKind, "status": quietWaiting, "uid": ref.Owner, "conversation_id": ref.ID,
		"dispatch_generation": generation, "due_at": due, "reconcile_after_at": due,
		"quiet_timeout_seconds": timeout.Seconds(), "updated_at": now, "created_at": created,
	}
	return finalization.QuietCheck{Ref: ref, Generation: generation, Due: due}, tx.Set(rows.jobPath, next)
}

// WakeQuiet reserves the next wake before returning a ready conversation.
func (s Store) WakeQuiet(ctx context.Context, a queue.Admitting, check finalization.QuietCheck) (finalization.QuietWake, error) {
	now := s.Clock.Now().UTC()
	wake, candidate, err := s.evaluateQuiet(ctx, a, check, now, archiveProof{})
	if err != nil || candidate.recording.id == "" {
		return wake, classify(err)
	}
	empty, proofErr := s.Archive.Empty(ctx, a, check.Ref, candidate.recording.id)
	candidate.checked, candidate.empty = true, empty && proofErr == nil
	wake, _, err = s.evaluateQuiet(ctx, a, check, s.Clock.Now().UTC(), candidate)
	return wake, classify(err)
}

func (s Store) evaluateQuiet(ctx context.Context, a queue.Admitting, check finalization.QuietCheck, now time.Time, proof archiveProof) (finalization.QuietWake, archiveProof, error) {
	var wake finalization.QuietWake
	var candidate archiveProof
	err := s.Docs.Fenced(ctx, a, check.Ref.Owner, func(tx *docstore.Tx) error {
		var wakeErr error
		wake, candidate, wakeErr = s.wakeQuiet(tx, check, now, proof)
		return wakeErr
	})
	return wake, candidate, err
}

func (s Store) wakeQuiet(tx *docstore.Tx, check finalization.QuietCheck, now time.Time, proof archiveProof) (finalization.QuietWake, archiveProof, error) {
	rows, err := getQuietRows(tx, check.Ref)
	if err != nil {
		return finalization.QuietWake{}, archiveProof{}, err
	}
	job, row := rows.job, rows.row
	if !currentQuiet(job, check.Generation) {
		return finalization.QuietWake{Action: rules.QuietStale}, archiveProof{}, nil
	}
	if due := field[time.Time](job, "due_at"); due.After(now) {
		check.Due = due
		return finalization.QuietWake{Check: check, Action: rules.QuietWait}, archiveProof{}, nil
	}

	recording, err := readRecordingLease(tx, check.Ref, row)
	if err != nil {
		return finalization.QuietWake{}, archiveProof{}, err
	}
	lease := recording.expiry
	timeout := rules.QuietTimeout(quietSeconds(job, "quiet_timeout_seconds"))
	action, due := rules.PlanQuietWake(now, quietDeadline(row, timeout), lease, quietEligible(row), s.hasInlineContent(check.Ref.Owner, row))
	wake := finalization.QuietWake{Action: action}
	switch action {
	case rules.QuietRetire:
		return wake, archiveProof{}, retireQuiet(tx, rows.jobPath, job, now, "")
	case rules.QuietRepair:
		return s.resolveQuietEmpty(tx, rows, check, wake, recording, now, proof)
	case rules.QuietStale:
		return wake, archiveProof{}, nil
	case rules.QuietWait, rules.QuietReady:
		if check.Generation == math.MaxInt64 {
			return finalization.QuietWake{}, archiveProof{}, finalization.ErrInvalid
		}
		check.Due, check.Generation = due, check.Generation+1
		wake.Check, wake.Cutoff = check, now.Add(-timeout)
		if producerEnd(row, now) {
			wake.Cutoff = now
		}
	}
	return wake, archiveProof{}, tx.Update(rows.jobPath, document{
		"dispatch_generation": check.Generation, "due_at": due, "reconcile_after_at": due, "updated_at": now,
	})
}

func currentQuiet(job document, generation int64) bool {
	return generation > 0 && field[string](job, "status") == quietWaiting && field[int64](job, "dispatch_generation") == generation
}

func retireQuiet(tx *docstore.Tx, path docstore.Ref, job document, now time.Time, reason string) error {
	if field[string](job, "status") != quietWaiting {
		return nil
	}
	delete(job, "reconcile_after_at")
	job["status"], job["updated_at"] = quietDone, now
	if reason != "" {
		job["last_failure_code"] = reason
	}
	return tx.Set(path, job)
}

func quietEligible(row document) bool {
	source := field[string](row, "source")
	return (source == "omi" || source == "phone") && field[string](row, "status") == string(rules.InProgress) &&
		!field[bool](row, "deleted") && !field[bool](row, "is_deleted") && !field[bool](row, "discarded") &&
		!field[bool](row, "is_locked") && field[string](row, "data_protection_level") != "private" &&
		field[string](row, "sync_merged_into") == "" && field[string](row, "finalization_job_id") == ""
}

func speechTime(row document) time.Time {
	for _, fieldName := range []string{"recorded_end", "last_speech_at", "finished_at"} {
		if stamp := field[time.Time](row, fieldName); !stamp.IsZero() {
			return stamp
		}
	}
	return time.Time{}
}

func quietDeadline(row document, timeout time.Duration) time.Time {
	last := speechTime(row)
	if last.IsZero() {
		return last
	}
	deadline := last.Add(timeout)
	if end := producerDeadline(row); !end.IsZero() && end.Before(deadline) {
		return end
	}
	return deadline
}

func producerDeadline(row document) time.Time {
	p := field[map[string]any](row, "listen_batch_producer")
	phase := field[string](p, "phase")
	if field[int64](p, "version") == 1 && (phase == "disconnected" || phase == "ended") && field[bool](p, "drained") {
		return field[time.Time](p, "deadline_at")
	}
	return time.Time{}
}

func producerEnd(row document, now time.Time) bool {
	end := producerDeadline(row)
	return !end.IsZero() && !end.After(now)
}

func quietSeconds(row document, key string) float64 {
	switch value := row[key].(type) {
	case int64:
		return float64(value)
	case float64:
		return value
	default:
		return 120
	}
}

// recordingLease binds an archive read to an exact recording document version,
// including custody changes that do not move the deadline.
type recordingLease struct {
	path            docstore.Ref
	id              string
	written, expiry time.Time
	sequence        int64
}

func recordingExpiry(tx *docstore.Tx, ref finalization.Ref, row document) (time.Time, error) {
	lease, err := readRecordingLease(tx, ref, row)
	return lease.expiry, err
}

func readRecordingLease(tx *docstore.Tx, ref finalization.Ref, row document) (recordingLease, error) {
	external := field[map[string]any](row, "external_data")
	sessionID := field[string](external, "recording_session_id")
	if sessionID == "" {
		return recordingLease{}, nil
	}
	path, err := docstore.Doc("users", ref.Owner, "recording_sessions", sessionID)
	if err != nil {
		return recordingLease{}, err
	}
	var session document
	written, err := tx.GetVersion(path, &session)
	if err != nil || written.IsZero() || field[string](session, "uid") != ref.Owner ||
		field[string](session, "recording_session_id") != sessionID || field[string](session, "conversation_id") != ref.ID ||
		field[string](session, "lifecycle_phase") != string(rules.InProgress) {
		return recordingLease{}, err
	}
	return recordingLease{path: path, id: sessionID, written: written, expiry: field[time.Time](session, "lease_expires_at"),
		sequence: field[int64](session, "lifecycle_sequence")}, nil
}
