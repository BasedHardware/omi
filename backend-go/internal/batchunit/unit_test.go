package batchunit_test

import (
	"encoding/json"
	"errors"
	"slices"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
)

func unit(id, ref string) batchunit.Unit {
	return batchunit.Unit{
		ID: id, Source: batchunit.Source{Ref: ref, Version: 7},
		OrderAt: time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC),
	}
}

func TestValidateNeedsIDSourceAndOrderTime(t *testing.T) {
	t.Parallel()
	if err := unit("u1", "audio/u1").Validate(); err != nil {
		t.Fatalf("a complete unit must be valid: %v", err)
	}
	missingOrder := unit("u1", "audio/u1")
	missingOrder.OrderAt = time.Time{}
	for name, u := range map[string]batchunit.Unit{
		"no id": unit("", "audio/u1"), "no source": unit("u1", ""), "no order time": missingOrder,
	} {
		if err := u.Validate(); !errors.Is(err, batchunit.ErrInvalid) {
			t.Errorf("%s: got %v, want ErrInvalid", name, err)
		}
	}
}

func TestNewJobPutsTheOwnerInItsOwnOrderedLane(t *testing.T) {
	t.Parallel()
	job, err := batchunit.NewJob("key-1", "owner-1", unit("u1", "audio/u1"))
	if err != nil {
		t.Fatal(err)
	}
	if job.Tenant != "owner-1" || job.OrderKey == nil || *job.OrderKey != "owner-1" {
		t.Errorf("owner must be both tenant and lane: %+v", job)
	}
	if job.Kind != batchunit.Kind || job.Format != batchunit.Format || job.Step != batchunit.StepSpeech ||
		job.SortKey != "u1" || job.Subject != "u1" {
		t.Errorf("unexpected job shape: %+v", job)
	}
	if job.Gated || job.Initializing || job.BudgetAllowed {
		t.Errorf("a unit is a plain job with no gate, binding step or budget requeue: %+v", job)
	}
}

func TestStoredInputIsAReferenceThatRoundTrips(t *testing.T) {
	t.Parallel()
	job, err := batchunit.NewJob("key-1", "owner-1", unit("u1", "audio/u1"))
	if err != nil {
		t.Fatal(err)
	}
	if string(job.Meta) != `{"ref":"audio/u1","version":7}` {
		t.Errorf("format 1 input changed shape: %s. A new shape is a new Format, not an edit", job.Meta)
	}
	source, err := batchunit.Input(job.Meta)
	if err != nil || source != (batchunit.Source{Ref: "audio/u1", Version: 7}) {
		t.Errorf("stored input does not round-trip: %+v, %v", source, err)
	}
}

func TestNewJobRejectsAnInvalidUnit(t *testing.T) {
	t.Parallel()
	if _, err := batchunit.NewJob("key-1", "owner-1", batchunit.Unit{}); !errors.Is(err, batchunit.ErrInvalid) {
		t.Fatalf("got %v, want ErrInvalid", err)
	}
}

func TestInputRejectsAnythingButASourceWithAReference(t *testing.T) {
	t.Parallel()
	for name, meta := range map[string]string{
		"json null": `null`, "empty object": `{}`, "a bare string": `"audio/u1"`,
		"no reference": `{"version":3}`, "not json": `{`, "nothing": ``,
	} {
		if _, err := batchunit.Input(json.RawMessage(meta)); !errors.Is(err, batchunit.ErrInvalid) {
			t.Errorf("%s: got %v, want ErrInvalid", name, err)
		}
	}
}

func TestStoredOnlyAcceptsACompleteReceipt(t *testing.T) {
	t.Parallel()
	for name, tc := range map[string]struct {
		checkpoint string
		want       bool
	}{
		"nothing saved":      {``, false},
		"json null":          {`null`, false},
		"empty object":       {`{}`, false},
		"no result location": {`{"operation":"op_1"}`, false},
		"no operation":       {`{"result":"results/u1"}`, false},
		"a bare string":      {`"hello"`, false},
		"a complete receipt": {`{"operation":"op_1","result":"results/u1"}`, true},
	} {
		if _, got := batchunit.Stored(json.RawMessage(tc.checkpoint)); got != tc.want {
			t.Errorf("%s: got %v, want %v", name, got, tc.want)
		}
	}
}

func TestCheckpointRefusesAnIncompleteReceipt(t *testing.T) {
	t.Parallel()
	if _, err := batchunit.Checkpoint(batchunit.Receipt{Operation: "op_1"}); !errors.Is(err, batchunit.ErrInvalid) {
		t.Errorf("got %v, want ErrInvalid", err)
	}
	encoded, err := batchunit.Checkpoint(batchunit.Receipt{Operation: "op_1", Result: "results/u1"})
	if err != nil {
		t.Fatal(err)
	}
	if receipt, ok := batchunit.Stored(encoded); !ok || receipt.Result != "results/u1" {
		t.Errorf("a saved receipt must read back: %+v %v", receipt, ok)
	}
}

func TestDeclarationListsEveryStepAndCause(t *testing.T) {
	t.Parallel()
	kind := batchunit.Declaration("vendor_down")
	if kind.Name != batchunit.Kind || len(kind.Formats) != 1 || kind.Formats[0] != batchunit.Format {
		t.Errorf("unexpected declaration: %+v", kind)
	}
	for _, step := range []string{batchunit.StepSpeech, batchunit.StepStored} {
		if !contains(kind.Steps, step) {
			t.Errorf("step %q is not declared", step)
		}
	}
	for _, cause := range []string{"vendor_down", string(batchunit.CauseInputUnreadable), string(batchunit.CauseStepFailed)} {
		found := false
		for _, declared := range kind.Causes {
			found = found || string(declared) == cause
		}
		if !found {
			t.Errorf("cause %q is not declared", cause)
		}
	}
}

func contains(list []string, want string) bool { return slices.Contains(list, want) }
