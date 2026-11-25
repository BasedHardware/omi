// Package batchunit is the reference job kind: read it before writing a new one.
//
// It transcribes one unit of an owner's batch, in the owner's order, paying for the
// transcription once and never losing a result it paid for. It shows the shape every kind
// follows:
//
//   - unit.go holds the kind's declaration, its types and its pure decisions. No I/O.
//   - ports.go declares the interfaces the kind needs from the outside world. The kind
//     never imports an adapter; the binary passes one in.
//   - service.go is the thin shell: admission and the queue handler.
package batchunit

import (
	"encoding/json"
	"errors"
	"slices"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Kind is the queue kind name.
const Kind = "batch_unit"

// Format is the version of the job's stored input and checkpoint. A change to either shape
// is a new format, declared beside the old one until no old job remains.
const Format = 1

const routedFormat = 2

// The kind's steps.
const (
	// StepSpeech means the transcription has not been stored yet.
	StepSpeech = "speech"
	// StepStored means the transcription is stored and the checkpoint holds its receipt.
	StepStored = "stored"
)

// The causes this kind returns on its own. An adapter's causes are declared with it.
const (
	// CauseInputUnreadable means a job's stored input could not be decoded. It cannot
	// happen for a job this package admitted; it is here so a corrupted row parks instead
	// of looping.
	CauseInputUnreadable queue.Cause = "batch_input_unreadable"
	// CauseStepFailed is recorded when a step fails with an error no adapter classified.
	CauseStepFailed queue.Cause = "batch_step_failed"
)

// Declaration is the kind's entry in the queue's registry. adapterCauses are the causes the
// adapters passed to Service can return; the binary supplies them when it wires the kind.
func Declaration(adapterCauses ...queue.Cause) queue.Kind {
	return queue.Kind{
		Name: Kind, PaidProcessing: true, Formats: []int{Format, routedFormat}, Steps: []string{StepSpeech, StepStored},
		Causes: slices.Concat([]queue.Cause{CauseInputUnreadable, CauseStepFailed}, adapterCauses),
	}
}

// ErrInvalid means a unit failed validation.
var ErrInvalid = errors.New("batchunit: unit needs an id, a source and an order time")

// Source points at a unit's input in the system that owns it. The job stores the pointer,
// never the input.
type Source struct {
	// Ref locates the input, for example an object path.
	Ref string
	// Version pins the exact contents, for example an object generation, so a retry reads
	// what the first attempt read.
	Version int64
}

// Route selects the speech adapter after funding admission. Empty is the legacy default.
type Route string

// Batch transcription routes.
const (
	Parakeet Route = "parakeet"
	Provider Route = "provider"
)

// Unit is one piece of an owner's batch.
type Unit struct {
	// ID identifies the unit within its owner.
	ID string
	// Source is where the input to transcribe lives.
	Source Source
	// OrderAt places the unit in the owner's order.
	OrderAt time.Time
	// BYOK and AlreadyPaid describe whether this unit needs platform-funded compute.
	BYOK, AlreadyPaid bool
	Route             Route
	// CustodyDeadline is supplied by intake from the existing retention clock.
	CustodyDeadline time.Time
	AudioDuration   time.Duration
	// RunAt optionally delays the unit.
	RunAt time.Time
}

// Validate reports whether the unit can be admitted.
func (u Unit) Validate() error {
	if u.ID == "" || u.Source.Ref == "" || u.OrderAt.IsZero() || (u.Route != "" && u.Route != Provider && u.Route != Parakeet) || u.AudioDuration < 0 {
		return ErrInvalid
	}
	return nil
}

// stored is the JSON shape of a job's input in format 1. It lives here, not on Unit, so the
// domain type can change without changing what old rows mean.
type stored struct {
	Ref     string `json:"ref"`
	Version int64  `json:"version"`
}

type routedInput struct {
	stored
	Route       Route `json:"route,omitempty"`
	BYOK        bool  `json:"byok,omitempty"`
	AlreadyPaid bool  `json:"already_paid,omitempty"`
}

// NewJob builds the queue job for a unit. key is the job's globally unique identity.
// The owner is both the tenant and the ordered lane, so an owner's units run one at a time,
// by OrderAt and then by unit id.
func NewJob(key, owner string, u Unit) (queue.NewJob, error) {
	if err := u.Validate(); err != nil {
		return queue.NewJob{}, err
	}
	format := Format
	var input any = stored(u.Source)
	if u.Route != "" || u.BYOK || u.AlreadyPaid || !u.CustodyDeadline.IsZero() {
		format = routedFormat
		input = routedInput{stored: stored(u.Source), Route: u.Route, BYOK: u.BYOK, AlreadyPaid: u.AlreadyPaid}
	}
	meta, err := json.Marshal(input)
	if err != nil {
		return queue.NewJob{}, errors.Join(ErrInvalid, err)
	}
	return queue.NewJob{
		Key: key, Tenant: owner, Kind: Kind, Format: format, Subject: u.ID, Step: StepSpeech, Meta: meta,
		FundingExempt: u.BYOK || u.AlreadyPaid, CustodyDeadline: u.CustodyDeadline, AudioDuration: u.AudioDuration,
		OrderKey: &owner, SortKey: u.ID, OrderAt: u.OrderAt, RunAt: u.RunAt,
	}, nil
}

// Input decodes a job's stored input. Anything but a source with a reference is rejected:
// JSON null, an empty object and a value of another type are all unreadable.
func Input(meta json.RawMessage) (Source, error) {
	in, err := processingInput(meta)
	return Source(in.stored), err
}

// Receipt proves a unit's transcription is stored. It is the whole checkpoint: where the
// result is, never the result.
type Receipt struct {
	// Operation is the identity of the paid call that produced the result.
	Operation string `json:"operation"`
	// Result locates the stored transcription in the system that owns it.
	Result string `json:"result"`
}

// Checkpoint encodes a receipt for Run.Save.
func Checkpoint(r Receipt) (json.RawMessage, error) {
	if r.Operation == "" || r.Result == "" {
		return nil, ErrInvalid
	}
	return json.Marshal(r)
}

// Stored returns the receipt a checkpoint holds. ok is false for a job that has stored
// nothing yet and for a checkpoint that is not a complete receipt: an empty object or a
// receipt missing a field is not proof of anything.
func Stored(checkpoint json.RawMessage) (Receipt, bool) {
	var r Receipt
	if json.Unmarshal(checkpoint, &r) != nil || r.Operation == "" || r.Result == "" {
		return Receipt{}, false
	}
	return r, true
}

func processingInput(meta json.RawMessage) (routedInput, error) {
	var input routedInput
	if err := json.Unmarshal(meta, &input); err != nil || input.Ref == "" {
		return routedInput{}, ErrInvalid
	}
	return input, nil
}
