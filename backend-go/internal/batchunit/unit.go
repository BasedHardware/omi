// Package batchunit is the reference job kind: read it before writing a new one.
//
// It transcribes one unit of an owner's batch, in the owner's order, paying for the
// transcription once. It shows the shape every kind follows:
//
//   - unit.go holds the kind's types and its pure decisions. No I/O.
//   - ports.go declares the interfaces the kind needs from the outside world. The kind
//     never imports an adapter; the binary passes one in.
//   - service.go is the thin shell: admission and the queue handler.
package batchunit

import (
	"encoding/json"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Kind is the queue kind name.
const Kind = "batch_unit"

// StepSpeech is the kind's only step.
const StepSpeech = "speech"

// CauseInputUnreadable means a job's stored input could not be decoded. It cannot happen for
// a job this package admitted; it is here so a corrupted row parks instead of looping.
const CauseInputUnreadable queue.Cause = "batch_input_unreadable"

// Causes lists every cause this kind returns on its own, for registration with the queue.
func Causes() []queue.Cause { return []queue.Cause{CauseInputUnreadable} }

// ErrInvalid means a unit failed validation.
var ErrInvalid = errors.New("batchunit: unit needs an id, an input and an order time")

// Unit is one piece of an owner's batch.
type Unit struct {
	// ID identifies the unit within its owner.
	ID string `json:"unit_id"`
	// Input is what to transcribe. A pointer so that "absent" and "empty" differ.
	Input *string `json:"input"`
	// OrderAt places the unit in the owner's order.
	OrderAt time.Time `json:"order_at"`
	// RunAt optionally delays the unit.
	RunAt time.Time `json:"run_at"`
}

// Validate reports whether the unit can be admitted.
func (u Unit) Validate() error {
	if u.ID == "" || u.Input == nil || u.OrderAt.IsZero() {
		return ErrInvalid
	}
	return nil
}

// NewJob builds the queue job for a unit. key is the job's globally unique identity.
// The owner is both the tenant and the ordered lane, so an owner's units run one at a time,
// by OrderAt and then by unit id.
func NewJob(key, owner string, u Unit) (queue.NewJob, error) {
	if err := u.Validate(); err != nil {
		return queue.NewJob{}, err
	}
	input, err := json.Marshal(*u.Input)
	if err != nil {
		return queue.NewJob{}, errors.Join(ErrInvalid, err)
	}
	return queue.NewJob{
		Key: key, Tenant: owner, Kind: Kind, Subject: u.ID, Step: StepSpeech, Meta: input,
		OrderKey: &owner, SortKey: u.ID, OrderAt: u.OrderAt, RunAt: u.RunAt,
	}, nil
}

// Done reports whether a job already holds its transcription. A stored result is never paid
// for again, including when a later claim only reconciles an exhausted job.
func Done(checkpoint json.RawMessage) bool {
	return len(checkpoint) > 0 && string(checkpoint) != "null"
}

// Input decodes a job's stored input.
func Input(meta json.RawMessage) (string, error) {
	var input string
	if err := json.Unmarshal(meta, &input); err != nil {
		return "", errors.Join(ErrInvalid, err)
	}
	return input, nil
}
