// Package finalization drives the conversation workflow using queue leases.
package finalization

import (
	"context"
	"encoding/json"
	"errors"
	"slices"
	"time"

	wire "github.com/BasedHardware/omi/backend-go/internal/conformance/stubapi"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const Kind = "finalization"

type Trigger string

const (
	CaptureEnd     Trigger = "capture_end"
	ClientFinalize Trigger = "client_finalize"
	ServerRecovery Trigger = "server_recovery"
	UserReprocess  Trigger = "user_reprocess"
)

type EndReason string

const (
	UserStop       EndReason = "user_stop"
	Silence        EndReason = "silence"
	Disconnect     EndReason = "disconnect"
	Timeout        EndReason = "timeout"
	ServerShutdown EndReason = "server_shutdown"
	Unknown        EndReason = "unknown"
)

type Admission struct {
	UID       string    `json:"uid"`
	Revision  int64     `json:"revision"`
	Trigger   Trigger   `json:"trigger"`
	EndReason EndReason `json:"end_reason"`
	RunAt     time.Time `json:"run_at"`
}

func (a Admission) Valid() bool {
	if a.UID == "" || a.Revision < 1 {
		return false
	}
	switch a.Trigger {
	case CaptureEnd, ClientFinalize, ServerRecovery, UserReprocess:
	default:
		return false
	}
	switch a.EndReason {
	case UserStop, Silence, Disconnect, Timeout, ServerShutdown, Unknown:
		return true
	default:
		return false
	}
}

type Refusal string

const (
	Missing          Refusal = "not_found"
	Tombstoned       Refusal = "conversation_tombstoned"
	AlreadyCompleted Refusal = "conversation_completed"
	AlreadyFailed    Refusal = "conversation_failed"
	Discarded        Refusal = "conversation_discarded"
	RevisionConflict Refusal = "revision_conflict"
	Deleting         Refusal = "account_deleting"
)

func (r Refusal) Error() string { return string(r) }

type Metadata struct {
	Trigger   Trigger   `json:"trigger"`
	EndReason EndReason `json:"end_reason"`
	Revision  int64     `json:"revision"`
	FanoutKey string    `json:"fanout_key"`
}

func Meta(j queue.Job) Metadata {
	var m Metadata
	// Only validated Admission records are written by this package; a row that does not
	// decode yields the zero Metadata, whose revision 0 never matches a bound document.
	if err := json.Unmarshal(j.Meta, &m); err != nil {
		return Metadata{}
	}
	return m
}

// The causes this flow produces itself. The stub adapter's causes are registered beside them.
const (
	CauseTranscriptUnreadable queue.Cause = "transcript_unreadable"
	CauseVectorFailed         queue.Cause = "vector_failed"
	CauseBYOKAbandoned        queue.Cause = "byok_session_abandoned"
)

// Causes lists every cause the flow can return on its own.
func Causes() []queue.Cause {
	return []queue.Cause{CauseTranscriptUnreadable, CauseVectorFailed, CauseBYOKAbandoned}
}

// Format is the version of the job's stored metadata and checkpoint.
const Format = 1

// Steps lists every step a finalization job can be at or time.
func Steps() []string {
	return []string{
		"load", "transcript", "discard", "notes", "persist", "claim", "memories", "vector", "integrations", "complete",
	}
}

// Declaration is the kind's entry in the queue's registry.
func Declaration(adapterCauses ...queue.Cause) queue.Kind {
	return queue.Kind{Name: Kind, Formats: []int{Format}, Steps: Steps(), Causes: slices.Concat(Causes(), adapterCauses)}
}

type Service struct {
	Store *queue.Store
	Wire  *wire.Client
	Codec crypt.Codec
	Warn  func(jobHash string, cause queue.Cause)
}

func (s *Service) Admit(ctx context.Context, cid string, a Admission) (string, error) {
	id := wire.ID("finalization", a.UID, cid, revisionString(a.Revision))
	canonical := id
	err := s.Store.Tenant(ctx, a.UID, func(sc *queue.Scope) error {
		return sc.Subject(ctx, Kind, cid, func() error {
			account, f := s.Wire.Account(ctx, a.UID)
			if f != nil {
				if f.Cause == wire.CauseAccountDeleting {
					return Deleting
				}
				return f
			}
			if account.Deleting {
				return Deleting
			}
			if _, err := sc.Get(ctx, id); err == nil {
				s.Wire.Dedupe(wire.Admission, true)
				return nil
			} else if !errors.Is(err, queue.ErrAbsent) {
				return err
			}

			d, f := s.Wire.Document(ctx, a.UID, cid)
			if f != nil {
				return admissionFault(f)
			}
			if d.Deleted || d.Tombstone {
				return Tombstoned
			}
			if d.DiscardedByUser || d.Status == "discarded" || d.Discarded {
				return Discarded
			}
			if d.Status == "processing" && d.Job != "" {
				canonical = d.Job
				s.Wire.Dedupe(wire.Admission, true)
				return nil
			}
			if refusal := canBind(d, a.Trigger, a.Revision); refusal != "" {
				return refusal
			}

			// A committed enqueue may still be reconciling a lost or failed
			// binding request. Keep a single admission intent for the subject.
			pending, err := sc.Active(ctx, Kind, cid)
			if err == nil {
				canonical = pending.Key
				s.Wire.Dedupe(wire.Admission, true)
				return nil
			}
			if !errors.Is(err, queue.ErrAbsent) {
				return err
			}
			meta, err := json.Marshal(Metadata{a.Trigger, a.EndReason, a.Revision, wire.ID("fanout", id)})
			if err != nil {
				return err
			}
			if _, _, err := sc.Enqueue(ctx, queue.NewJob{
				Key: id, Tenant: a.UID, Kind: Kind, Format: Format, Subject: cid, Step: "load", Meta: meta,
				Gated: account.OwnKey, Initializing: true, BudgetAllowed: true, RunAt: a.RunAt,
			}); err != nil {
				return err
			}
			s.Wire.Dedupe(wire.Admission, false)
			if _, f = s.Wire.Patch(ctx, a.UID, cid, d.Version, binding(id, a.Revision)); f == nil {
				// Admission is durable: if activation fails here, the initializing job is
				// due again within a second and a worker activates it.
				if err := sc.Activate(ctx, id); err != nil {
					s.Warn(wire.Digest(id)[:16], wire.CauseTransport)
				}
			} else if f.Cause == wire.CauseAccountDeleting || f.Status == 404 || f.Status == 410 {
				if err := sc.CancelInitialization(ctx, id); err != nil {
					return err
				}
				if f.Cause == wire.CauseAccountDeleting {
					return Deleting
				}
				return admissionFault(f)
			}
			return nil
		})
	})
	return canonical, err
}

func admissionFault(f *wire.Fault) error {
	switch f.Status {
	case 404:
		return Missing
	case 410:
		return Tombstoned
	default:
		return f
	}
}

func canBind(d wire.Document, trigger Trigger, revision int64) Refusal {
	if d.Status == "processing" && d.Job != "" {
		return RevisionConflict
	}
	if d.Status == "completed" || d.Status == "failed" {
		if trigger != UserReprocess {
			if d.Status == "completed" {
				return AlreadyCompleted
			}
			return AlreadyFailed
		}
		bound := max(1, d.Revision)
		if revision <= bound {
			return RevisionConflict
		}
		return ""
	}
	if d.Revision == 0 && revision != 1 || d.Revision != 0 && revision <= d.Revision {
		return RevisionConflict
	}
	return ""
}

func binding(id string, revision int64) wire.Patch {
	return wire.Patch{
		"status": "processing", "finalization_job_id": id, "finalization_revision": revision,
		"finalization_status": nil, "summary_retryable": nil, "fanout_state": nil, "fanout_key": nil,
		"notes_llm_input_hash": nil, "jobd_notes": nil, "memories_llm_input_hash": nil, "jobd_memories": nil,
	}
}
