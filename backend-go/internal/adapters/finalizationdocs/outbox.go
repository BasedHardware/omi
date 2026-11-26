// Package finalizationdocs owns ordinary finalization job documents and their
// transactions with the conversation binding.
package finalizationdocs

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const jobs = "conversation_finalization_jobs"

const (
	queued     = "queued"
	blocked    = "blocked_byok"
	leased     = "leased"
	completed  = "completed"
	deadLetter = "dead_letter"
)

// Store is the fenced Firestore persistence for finalization's ordinary intents.
type Store struct {
	Docs            *docstore.Store
	Codec           crypt.Codec
	Clock           clock.Clock
	Archive         ClosedArchive
	MergeRetraction MergeRetraction
	SyncOnly        bool
}

// ErrUnsupported identifies admission paths needing recovery or backfill evidence
// this adapter cannot yet establish transactionally.
var ErrUnsupported = errors.New("finalization documents: unsupported admission trigger")

// Causes are the closed queue labels used by this persistence boundary.
const (
	CauseDeleting     queue.Cause = "finalization_owner_deleting"
	CauseUnavailable  queue.Cause = "finalization_documents_unavailable"
	CauseForeignLease queue.Cause = "finalization_foreign_lease"
	CauseRejected     queue.Cause = "finalization_documents_rejected"
)

func classify(err error) error {
	var fault *docstore.CallError
	switch {
	case err == nil, errors.Is(err, queue.ErrLease), errors.Is(err, context.Canceled), errors.Is(err, finalization.ErrStale):
		return err
	case errors.Is(err, docstore.ErrOwnerDeleting):
		return queue.Classify(err, queue.Hold(CauseDeleting, time.Minute))
	case errors.Is(err, docstore.ErrExists), errors.Is(err, context.DeadlineExceeded),
		errors.As(err, &fault) && fault.Kind == docstore.KindTransient:
		return queue.Classify(err, queue.Retry(CauseUnavailable, 0))
	default:
		return queue.Classify(err, queue.Fail(CauseRejected))
	}
}

// Causes declares all queue outcomes emitted by this adapter.
func Causes() []queue.Cause {
	return []queue.Cause{CauseDeleting, CauseUnavailable, CauseRejected, CauseForeignLease}
}

type document map[string]any

func field[T any](row document, key string) T {
	if value, ok := row[key].(T); ok {
		return value
	}
	var zero T
	return zero
}

// Admit binds an ordinary capture intent and its deterministic job in one
// transaction. The Firestore job exists before the service attempts SQL enqueue.
func (s Store) Admit(ctx context.Context, a queue.Admitting, req finalization.AdmissionRequest, decide func(rules.AdmissionFacts) rules.AdmissionAction) (finalization.Intent, error) {
	if s.SyncOnly {
		// Producer admission and the handback protocol are wired separately.
		return finalization.Intent{}, ErrUnsupported
	}
	if req.Trigger != rules.CaptureEnd && req.Trigger != rules.ClientFinalize && req.Trigger != rules.ServerRecovery {
		return finalization.Intent{}, ErrUnsupported
	}
	ref, err := conversationRef(req.Ref)
	if err != nil {
		return finalization.Intent{}, classify(err)
	}
	now := s.Clock.Now().UTC()
	var intent finalization.Intent
	err = s.Docs.Fenced(ctx, a, req.Ref.Owner, func(tx *docstore.Tx) error {
		var txnErr error
		intent, txnErr = s.admit(tx, ref, req, now, decide)
		return txnErr
	})
	if err != nil {
		return finalization.Intent{}, classify(err)
	}
	return intent, nil
}

func conversationRef(ref finalization.Ref) (docstore.Ref, error) {
	return docstore.Doc("users", ref.Owner, "conversations", ref.ID)
}

func (s Store) admit(tx *docstore.Tx, ref docstore.Ref, req finalization.AdmissionRequest, now time.Time, decide func(rules.AdmissionFacts) rules.AdmissionAction) (finalization.Intent, error) {
	var row document
	found, err := tx.Get(ref, &row)
	if err != nil || !found {
		return finalization.Intent{}, err
	}
	binding := field[string](row, "finalization_job_id")
	revision := field[int64](row, "finalization_revision")
	existing, err := getIntent(tx, req.Ref, binding, revision)
	if err != nil {
		return finalization.Intent{}, err
	}
	facts := rules.AdmissionFacts{
		Status: rules.Status(field[string](row, "status")), Deleted: field[bool](row, "deleted") || field[bool](row, "is_deleted"),
		Discarded: field[bool](row, "discarded"), Deferred: field[bool](row, "deferred"),
		Protected:  field[bool](row, "is_locked") || field[string](row, "data_protection_level") == "private",
		HasContent: s.hasInlineContent(req.Ref.Owner, row), ExistingJob: existing.JobID != "", HasBinding: binding != "",
	}
	var quiet quietRows
	if req.Trigger == rules.ServerRecovery {
		var allowed bool
		quiet, allowed, err = prepareRecovery(tx, req, row, now, &facts)
		if err != nil || !allowed {
			return finalization.Intent{}, err
		}
	}
	switch decide(facts) {
	case rules.Refuse:
		return finalization.Intent{}, nil
	case rules.UseBound:
		return existing, nil
	case rules.BindNext:
		if revision < 0 || revision == math.MaxInt64 {
			return finalization.Intent{}, finalization.ErrInvalid
		}
		intent, bindErr := bind(tx, ref, row, req, revision+1, now)
		if bindErr == nil && intent.JobID != "" && quiet.job != nil {
			bindErr = retireQuiet(tx, quiet.jobPath, quiet.job, now, "")
		}
		return intent, bindErr
	}
	return finalization.Intent{}, finalization.ErrInvalid
}

func (s Store) hasInlineContent(owner string, row document) bool {
	if field[bool](row, "has_content") || len(field[[]any](row, "photos")) > 0 ||
		(field[string](row, "record_lane_owner") == "batch_live_v1" && len(field[[]any](row, "audio_files")) > 0) {
		return true
	}
	compressed := field[bool](row, "transcript_segments_compressed")
	var value any
	switch raw := row["transcript_segments"].(type) {
	case nil:
		return false
	case []any:
		return len(raw) > 0
	case []byte:
		value = map[string][]byte{"base64": raw}
	case string:
		value = raw
	default:
		// An unreadable transcript or lake pointer is not proof of empty custody.
		return true
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return true
	}
	segments, err := s.Codec.Decode(owner, crypt.Transcript{Segments: encoded, Compressed: compressed})
	return err != nil || len(segments) > 0
}

func getIntent(tx *docstore.Tx, ref finalization.Ref, id string, revision int64) (finalization.Intent, error) {
	if id == "" {
		return finalization.Intent{}, nil
	}
	path, err := docstore.Doc(jobs, id)
	if err != nil {
		return finalization.Intent{}, err
	}
	var row document
	found, err := tx.Get(path, &row)
	if err != nil || !found {
		return finalization.Intent{}, err
	}
	return readIntent(ref, row, id, revision)
}

func readIntent(ref finalization.Ref, row document, id string, revision int64) (finalization.Intent, error) {
	trigger := rules.Trigger(field[string](row, "processing_trigger"))
	if trigger == "" {
		trigger = rules.CaptureEnd
		if field[bool](row, "force_process") {
			trigger = rules.ClientFinalize
		}
	}
	if field[string](row, "uid") != ref.Owner || field[string](row, "conversation_id") != ref.ID ||
		field[int64](row, "finalization_revision") != revision || revision < 1 || finalization.JobID(ref, revision) != id {
		return finalization.Intent{}, finalization.ErrInvalid
	}
	if _, known := rules.ProcessingMode(trigger); !known {
		return finalization.Intent{}, finalization.ErrInvalid
	}
	return finalization.Intent{Ref: ref, JobID: id, Revision: revision, Trigger: trigger, RequiresBYOK: field[bool](row, "requires_byok")}, nil
}

func bind(tx *docstore.Tx, ref docstore.Ref, row document, req finalization.AdmissionRequest, revision int64, now time.Time) (finalization.Intent, error) {
	id := finalization.JobID(req.Ref, revision)
	path, err := docstore.Doc(jobs, id)
	if err != nil {
		return finalization.Intent{}, err
	}
	var job document
	found, err := tx.Get(path, &job)
	if err != nil {
		return finalization.Intent{}, err
	}
	if found && terminal(job) != finalization.TerminalPending {
		return finalization.Intent{}, nil
	}
	if !found {
		job = newJob(row, req, revision, id, now)
		initial := field[string](job, "status")
		if projectErr := addProjection(tx, job, map[string]int64{"accepted": 1, initial: 1}); projectErr != nil {
			return finalization.Intent{}, projectErr
		}
		if createErr := tx.Create(path, job); createErr != nil {
			return finalization.Intent{}, createErr
		}
	}
	intent, err := readIntent(req.Ref, job, id, revision)
	if err != nil {
		return finalization.Intent{}, err
	}
	return intent, tx.Update(ref, document{
		"status": string(rules.Processing), "finalization_job_id": id, "finalization_revision": revision,
		"finalization_status": field[string](job, "status"),
	})
}

func newJob(row document, req finalization.AdmissionRequest, revision int64, id string, now time.Time) document {
	mode, _ := rules.ProcessingMode(req.Trigger)
	requiresBYOK := req.RequiresBYOK || field[bool](row, "listen_finalization_requires_byok")
	job := document{
		"uid": req.Ref.Owner, "conversation_id": req.Ref.ID, "finalization_revision": revision,
		"schema_version": int64(1), "processing_trigger": string(req.Trigger), "force_process": mode.RunNow,
		"client_platform": field[string](row, "client_platform"), "requires_byok": requiresBYOK,
		"fanout_key":    fmt.Sprintf("conversation:%s:finalization:%d", req.Ref.ID, revision),
		"fanout_status": "pending", "status": queued, "dispatch_generation": int64(1),
		"attempt_count": int64(0), "task_retry_count": int64(0), "worker_claim_count": int64(0),
		"created_at": now, "updated_at": now, "dispatch_requested_at": now,
		"projection_generation": projectionGeneration, "projection_shard": projectionShard(id),
	}
	if requiresBYOK {
		job["status"], job["blocked_byok_at"] = blocked, now
	} else {
		job["reconcile_after_at"] = now.Add(finalization.ReconcileStaleness)
	}
	return job
}
