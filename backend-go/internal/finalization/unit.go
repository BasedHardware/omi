// Package finalization runs a conversation's ordinary finalization intent.
package finalization

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	// Kind identifies the ordinary finalization queue family.
	Kind = "finalization"
	// Format distinguishes durable intents from the conformance-only job format.
	Format = 2
	// StepLoad reads the bound snapshot.
	StepLoad = "load"
	// StepNotes requests and persists structure.
	StepNotes = "notes"
	// StepFanout acquires and completes durable delivery.
	StepFanout = "fanout"
)

// Closed causes emitted by the finalization family.
const (
	CauseInvalid         queue.Cause = "finalization_invalid"
	CauseStore           queue.Cause = "finalization_store"
	CauseStale           queue.Cause = "finalization_stale"
	CauseChanged         queue.Cause = "finalization_source_changed"
	CauseEpisodeNotes    queue.Cause = "finalization_episode_notes_pending"
	CauseArchiveOpen     queue.Cause = "finalization_archive_open"
	CauseDeliveryDropped queue.Cause = "integration_dropped"
)

// Declaration registers this format and the closed causes that its collaborators can return.
func Declaration(adapterCauses ...queue.Cause) queue.Kind {
	causes := []queue.Cause{CauseInvalid, CauseStore, CauseStale, CauseChanged, CauseArchiveOpen, CauseEpisodeNotes, CauseDeliveryDropped}
	for _, cause := range adapterCauses {
		if !slices.Contains(causes, cause) {
			causes = append(causes, cause)
		}
	}
	return queue.Kind{Name: Kind, Formats: []int{Format}, Steps: []string{StepLoad, StepNotes, StepFanout}, Causes: causes}
}

var (
	// ErrInvalid indicates an invalid or incompatible intent.
	ErrInvalid = errors.New("finalization: invalid intent")
	// ErrDispatchUnavailable indicates the caller required durable dispatch.
	ErrDispatchUnavailable = errors.New("finalization: required durable dispatch unavailable")
	// ErrCompletionAbsent means recovery found no committed notes response.
	ErrCompletionAbsent = errors.New("finalization: no committed completion")
	// ErrStale fences work for a missing or superseded conversation.
	ErrStale = errors.New("finalization: conversation is missing or no longer bound")
)

// Ref locates a conversation under its owner.
type Ref struct {
	Owner, ID string
}

// Intent is the durable outbox entry, without transcript or credentials.
type Intent struct {
	Ref          Ref
	JobID        string
	Revision     int64
	Trigger      rules.Trigger
	RequiresBYOK bool
}

// AdmissionRequest supplies the entry point's dispatch policy and recovery evidence.
type AdmissionRequest struct {
	Ref                     Ref
	Trigger                 rules.Trigger
	RequiresBYOK            bool
	RequiresDispatch        bool
	DispatchAvailable       bool
	RecoveryCutoff          time.Time
	QuietGeneration         int64
	RequireExpiredLease     bool
	BackfillRunID           string
	ExpectedUpdateTime      time.Time
	ExpectedSessionRevision string
}

// JobID is the stable Firestore id for a conversation's immutable revision. The
// UUID version and variant bits match Python's document_id_from_seed.
func JobID(ref Ref, revision int64) string {
	sum := sha256.Sum256(fmt.Appendf(nil, "listen-finalization:%s:%s:%d", ref.Owner, ref.ID, revision))
	sum[6] = sum[6]&0x0f | 0x40
	sum[8] = sum[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", sum[:4], sum[4:6], sum[6:8], sum[8:10], sum[10:16])
}

type stored struct {
	Revision int64         `json:"revision"`
	Trigger  rules.Trigger `json:"trigger"`
}

func (in Intent) valid() bool {
	_, known := rules.ProcessingMode(in.Trigger)
	return known && in.Ref.Owner != "" && in.Ref.ID != "" && in.Revision > 0 && in.JobID == JobID(in.Ref, in.Revision)
}

func (in Intent) newJob() (queue.NewJob, error) {
	if !in.valid() {
		return queue.NewJob{}, ErrInvalid
	}
	meta, err := json.Marshal(stored{Revision: in.Revision, Trigger: in.Trigger})
	if err != nil {
		return queue.NewJob{}, err
	}
	return queue.NewJob{
		Key: in.JobID, Tenant: in.Ref.Owner, Kind: Kind, Format: Format, Subject: in.Ref.ID,
		Step: StepLoad, Meta: meta, Gated: in.RequiresBYOK,
		BudgetAllowed: !in.RequiresBYOK && in.Trigger != rules.SilentBackfill,
	}, nil
}

func readIntent(job queue.Job) (Intent, error) {
	var meta stored
	if job.Format != Format || json.Unmarshal(job.Meta, &meta) != nil {
		return Intent{}, ErrInvalid
	}
	in := Intent{
		Ref: Ref{Owner: job.Tenant, ID: job.Subject}, JobID: job.Key, Revision: meta.Revision,
		Trigger: meta.Trigger, RequiresBYOK: job.Gated,
	}
	if !in.valid() {
		return Intent{}, ErrInvalid
	}
	return in, nil
}

// ReconcileStaleness is the default delay before revisiting a queued dispatch.
const ReconcileStaleness = 5 * time.Minute

// Defaults returns the ordinary finalization lease, gated inactivity period,
// deterministic cap and delayed budget grant. The binary must combine these
// with its transient and reconciliation budgets.
func Defaults() (lease, gateTimeout, budgetDelay time.Duration, deterministicMax int) {
	return 1500 * time.Second, 14 * 24 * time.Hour, 2700 * time.Second, 4
}
