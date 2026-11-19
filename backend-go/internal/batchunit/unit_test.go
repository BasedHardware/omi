package batchunit_test

import (
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
)

func unit(id, input string) batchunit.Unit {
	return batchunit.Unit{ID: id, Input: &input, OrderAt: time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)}
}

func TestValidateNeedsIDInputAndOrderTime(t *testing.T) {
	t.Parallel()
	if err := unit("u1", "").Validate(); err != nil {
		t.Fatalf("an empty input string is a valid input: %v", err)
	}
	missingInput := unit("u1", "x")
	missingInput.Input = nil
	missingOrder := unit("u1", "x")
	missingOrder.OrderAt = time.Time{}
	for name, u := range map[string]batchunit.Unit{
		"no id": unit("", "x"), "no input": missingInput, "no order time": missingOrder,
	} {
		if err := u.Validate(); !errors.Is(err, batchunit.ErrInvalid) {
			t.Errorf("%s: got %v, want ErrInvalid", name, err)
		}
	}
}

func TestNewJobPutsTheOwnerInItsOwnOrderedLane(t *testing.T) {
	t.Parallel()
	job, err := batchunit.NewJob("key-1", "owner-1", unit("u1", "hello"))
	if err != nil {
		t.Fatal(err)
	}
	if job.Tenant != "owner-1" || job.OrderKey == nil || *job.OrderKey != "owner-1" {
		t.Errorf("owner must be both tenant and lane: %+v", job)
	}
	if job.Kind != batchunit.Kind || job.Step != batchunit.StepSpeech || job.SortKey != "u1" || job.Subject != "u1" {
		t.Errorf("unexpected job shape: %+v", job)
	}
	if job.Gated || job.Initializing || job.BudgetAllowed {
		t.Errorf("a unit is a plain job with no gate, binding step or budget requeue: %+v", job)
	}
	input, err := batchunit.Input(job.Meta)
	if err != nil || input != "hello" {
		t.Errorf("stored input does not round-trip: %q, %v", input, err)
	}
}

func TestNewJobRejectsAnInvalidUnit(t *testing.T) {
	t.Parallel()
	if _, err := batchunit.NewJob("key-1", "owner-1", batchunit.Unit{}); !errors.Is(err, batchunit.ErrInvalid) {
		t.Fatalf("got %v, want ErrInvalid", err)
	}
}

func TestDoneOnlyWhenAResultIsStored(t *testing.T) {
	t.Parallel()
	for name, tc := range map[string]struct {
		checkpoint json.RawMessage
		want       bool
	}{
		"nothing stored":  {nil, false},
		"json null":       {json.RawMessage("null"), false},
		"empty result":    {json.RawMessage(`""`), true},
		"a transcription": {json.RawMessage(`"hello"`), true},
	} {
		if got := batchunit.Done(tc.checkpoint); got != tc.want {
			t.Errorf("%s: got %v, want %v", name, got, tc.want)
		}
	}
}

func TestInputRejectsAStoredValueThatIsNotAString(t *testing.T) {
	t.Parallel()
	if _, err := batchunit.Input(json.RawMessage(`{"not":"a string"}`)); !errors.Is(err, batchunit.ErrInvalid) {
		t.Fatalf("got %v, want ErrInvalid", err)
	}
}
