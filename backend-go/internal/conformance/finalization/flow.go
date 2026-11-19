package finalization

import (
	"context"
	"errors"
	"strconv"
	"unicode"

	wire "github.com/BasedHardware/omi/backend-go/internal/conformance/stubapi"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func revisionString(n int64) string { return strconv.FormatInt(n, 10) }

type flow struct {
	*Service
	// ctx is the handler's context for this one run. The flow is created and dropped inside
	// a single Work or Exhausted call, so it never outlives the call it belongs to.
	ctx          context.Context
	r            *queue.Run
	meta         Metadata
	doc          wire.Document
	account      wire.Account
	vendorKey    string
	inputVersion int64
	inputText    string
}

func (s *Service) run(ctx context.Context, r *queue.Run) *flow {
	return &flow{Service: s, ctx: ctx, r: r, meta: Meta(r.Job)}
}

func (s *Service) Work(ctx context.Context, r *queue.Run) queue.Outcome {
	f := s.run(ctx, r)
	check := accountCheck(r)
	if check.Fault != nil {
		return check.Fault.Outcome()
	}
	f.account = check.Account
	if err := f.load(); err != nil {
		return wire.Outcome(err)
	}

	if !f.bound(f.doc) {
		if !r.Job.Initializing || f.unavailable(f.doc) || f.doc.Discarded ||
			canBind(f.doc, f.meta.Trigger, f.meta.Revision) != "" {
			return queue.Fence(wire.CauseConversationFenced)
		}
		err := f.patch(func(d wire.Document) (wire.Patch, *wire.Fault) {
			if f.bound(d) {
				return nil, nil
			}
			if f.unavailable(d) || d.Discarded || canBind(d, f.meta.Trigger, f.meta.Revision) != "" {
				return nil, conversationFence()
			}
			return binding(r.Job.Key, f.meta.Revision), nil
		})
		if err != nil {
			return wire.Outcome(err)
		}
	}
	if f.unavailable(f.doc) {
		return queue.Fence(wire.CauseConversationFenced)
	}
	if r.Job.Initializing {
		if f.account.OwnKey && !r.Job.Gated {
			return queue.BlockForSecret()
		}
		return queue.Activate()
	}
	if f.finished() {
		return f.success()
	}
	if f.account.OwnKey || r.Job.Gated {
		if r.Secret == "" {
			return queue.BlockForSecret()
		}
		if !f.account.OwnKey {
			// A previously own-key job cannot switch to platform credentials.
			return queue.Fail(wire.CauseVendorRejected)
		}
		f.vendorKey = r.Secret
	} else {
		f.vendorKey = "platform"
	}

	if f.doc.FinalizationStatus == "dead_letter" {
		if err := f.reopen(); err != nil {
			return wire.Outcome(err)
		}
	}

	input, words, err := f.transcript()
	if err != nil {
		return wire.Outcome(err)
	}
	if f.doc.Status != "completed" {
		if err := f.notes(input, words); err != nil {
			return wire.Outcome(err)
		}
	}
	if f.doc.Discarded {
		return f.success()
	}
	if err := f.claim(); err != nil {
		return wire.Outcome(err)
	}
	if err := f.fanout(input); err != nil {
		return wire.Outcome(err)
	}
	return f.success()
}

func (f *flow) load() error {
	defer f.r.Observe("load")()
	return wire.Guard(f.ctx, f.r, func(ctx context.Context) (fault *wire.Fault) {
		f.doc, fault = f.Wire.Document(ctx, f.r.Job.Tenant, f.r.Job.Subject)
		return
	})
}

func (f *flow) bound(d wire.Document) bool {
	return d.Job == f.r.Job.Key && d.Revision == f.meta.Revision
}

func (f *flow) unavailable(d wire.Document) bool {
	return d.Deleted || d.Tombstone || d.DiscardedByUser || d.Status == "discarded" || (d.Discarded && d.Status != "completed")
}

func (f *flow) usable(d wire.Document) *wire.Fault {
	if f.unavailable(d) || !f.bound(d) {
		return conversationFence()
	}
	return nil
}

func conversationFence() *wire.Fault {
	return &wire.Fault{Result: wire.Fenced, Cause: wire.CauseConversationFenced}
}

func versionConflict() *wire.Fault {
	return &wire.Fault{Result: wire.Deterministic, Cause: wire.CauseVersionConflict}
}

func unreadable() *wire.Fault {
	return &wire.Fault{Result: wire.Deterministic, Cause: CauseTranscriptUnreadable}
}

func (f *flow) patch(build func(wire.Document) (wire.Patch, *wire.Fault)) error {
	j := f.r.Job
	return wire.Guard(f.ctx, f.r, func(ctx context.Context) *wire.Fault {
		for range 4 {
			p, err := build(f.doc)
			if err != nil || p == nil {
				return err
			}
			next, err := f.Wire.Patch(ctx, j.Tenant, j.Subject, f.doc.Version, p)
			if err == nil {
				if f.inputVersion == f.doc.Version {
					// Workflow patches do not modify transcripts.
					f.inputVersion = next.Version
				}
				f.doc = next
				return nil
			}
			if err.Cause != wire.CauseVersionConflict {
				return err
			}
			f.doc, err = f.Wire.Document(ctx, j.Tenant, j.Subject)
			if err != nil {
				return err
			}
		}
		return versionConflict()
	})
}

func (f *flow) finished() bool {
	return f.doc.Status == "completed" && f.doc.FinalizationStatus != "dead_letter" &&
		(f.doc.Discarded || f.doc.FanoutState == "completed")
}

func (f *flow) reopen() error {
	return f.patch(func(d wire.Document) (wire.Patch, *wire.Fault) {
		if e := f.usable(d); e != nil {
			return nil, e
		}
		if d.FinalizationStatus != "dead_letter" {
			return nil, nil
		}
		return wire.Patch{"status": "processing", "finalization_status": nil, "summary_retryable": nil}, nil
	})
}

func (f *flow) transcript() (input string, words int, err error) {
	decoded := func() (string, error) {
		defer f.r.Observe("transcript")()
		return f.Codec.DecodeText(f.r.Job.Tenant, f.doc.Transcript)
	}
	input, err = decoded()
	if err != nil {
		if e := f.r.SetStep(f.ctx, "transcript"); e != nil {
			return "", 0, e
		}
		return "", 0, unreadable()
	}
	f.inputVersion, f.inputText = f.doc.Version, input
	defer f.r.Observe("discard")()
	inWord := false
	for _, r := range input {
		space := unicode.IsSpace(r) || (r >= '\u001c' && r <= '\u001f')
		if !space && !inWord {
			words++
		}
		inWord = !space
	}
	return input, words, nil
}

func (f *flow) notes(text string, words int) error {
	j := f.r.Job
	discard := words < f.account.MinWords
	input := wire.Input(j, "notes", text)
	var notes wire.NotesOutput
	if !discard {
		if err := f.r.SetStep(f.ctx, "notes"); err != nil {
			return err
		}
		var err error
		notes, err = f.noteOutput(input)
		if err != nil {
			return err
		}
	}
	if err := f.r.SetStep(f.ctx, "persist"); err != nil {
		return err
	}
	defer f.r.Observe("persist")()
	return f.patch(func(d wire.Document) (wire.Patch, *wire.Fault) {
		if e := f.usable(d); e != nil {
			return nil, e
		}
		if d.Status == "completed" && d.FinalizationStatus != "dead_letter" {
			return nil, nil
		}
		if d.Status != "processing" {
			return nil, conversationFence()
		}
		if e := f.sameInput(d, input); e != nil {
			return nil, e
		}
		p := wire.Patch{"status": "completed", "structured": notes, "discarded": discard,
			"finalization_status": nil, "summary_retryable": nil, "jobd_notes": nil}
		if !discard {
			p["notes_llm_input_hash"] = input.Hash
		}
		return p, nil
	})
}

func (f *flow) sameInput(d wire.Document, in wire.VendorInput) *wire.Fault {
	if f.inputVersion != d.Version {
		input, err := f.Codec.DecodeText(f.r.Job.Tenant, d.Transcript)
		if err != nil {
			return unreadable()
		}
		f.inputVersion, f.inputText = d.Version, input
	}
	if f.inputText != in.Input {
		return versionConflict()
	}
	return nil
}

func (f *flow) noteOutput(in wire.VendorInput) (wire.NotesOutput, error) {
	defer f.r.Observe("notes")()
	var notes wire.NotesOutput
	if f.doc.NotesHash == in.Hash && f.doc.NotesCache != nil {
		f.Wire.Dedupe(wire.Notes, true)
		return *f.doc.NotesCache, nil
	}
	f.Wire.Dedupe(wire.Notes, false)
	err := wire.Guard(f.ctx, f.r, func(ctx context.Context) (fault *wire.Fault) {
		notes, fault = f.Wire.Notes(ctx, in, f.vendorKey)
		return
	})
	if err != nil {
		return notes, err
	}
	err = f.patch(func(d wire.Document) (wire.Patch, *wire.Fault) {
		if e := f.usable(d); e != nil {
			return nil, e
		}
		if d.Discarded || d.Status != "processing" {
			return nil, conversationFence()
		}
		if e := f.sameInput(d, in); e != nil {
			return nil, e
		}
		return wire.Patch{"notes_llm_input_hash": in.Hash, "jobd_notes": notes}, nil
	})
	return notes, err
}

func (f *flow) claim() error {
	defer f.r.Observe("claim")()
	if f.doc.FanoutState == "claimed" && f.doc.FanoutKey == f.meta.FanoutKey {
		return nil
	}
	if err := f.r.SetStep(f.ctx, "claim"); err != nil {
		return err
	}
	return f.patch(func(d wire.Document) (wire.Patch, *wire.Fault) {
		if e := f.canFanout(d); e != nil {
			return nil, e
		}
		if d.FanoutState == "completed" {
			return nil, nil
		}
		return wire.Patch{"fanout_state": "claimed", "fanout_key": f.meta.FanoutKey}, nil
	})
}

func (f *flow) canFanout(d wire.Document) *wire.Fault {
	if e := f.usable(d); e != nil {
		return e
	}
	if d.Status != "completed" || d.Discarded {
		return conversationFence()
	}
	return nil
}

func (s *Service) Exhausted(ctx context.Context, r *queue.Run, cause queue.Cause, transient bool) queue.Outcome {
	f := s.run(ctx, r)
	if err := f.load(); err != nil {
		return reconcileError(err)
	}
	if f.unavailable(f.doc) {
		return queue.Fence(wire.CauseConversationFenced)
	}
	if !f.bound(f.doc) {
		if r.Job.Initializing {
			return queue.Fail(cause)
		}
		return queue.Fence(wire.CauseConversationFenced)
	}
	if f.finished() {
		return f.success()
	}
	if cause == queue.CauseLeaseExpired && (!r.Job.Gated || r.Secret != "") && f.doc.FanoutState == "claimed" &&
		(r.Job.Step == "integrations" || r.Job.Step == "complete") {
		check := accountCheck(r)
		if check.Fault == nil {
			f.account = check.Account
			err := f.finishFanout(f.progress())
			if err == nil || f.finished() {
				return f.success()
			}
			var fault *wire.Fault
			if errors.As(err, &fault) && (fault.Result == wire.Fenced || fault.Result == wire.Yielded) {
				return fault.Outcome()
			}
			if errors.Is(err, queue.ErrLease) || errors.Is(err, context.Canceled) {
				return queue.Abort()
			}
		}
	}
	if r.WillBudgetRequeue() {
		return queue.Fail(cause)
	}
	if f.doc.Status == "processing" {
		err := f.patch(func(d wire.Document) (wire.Patch, *wire.Fault) {
			if e := f.usable(d); e != nil {
				return nil, e
			}
			if d.Status != "processing" || d.Discarded {
				return nil, nil
			}
			p := wire.Patch{"status": "completed", "finalization_status": "dead_letter", "summary_retryable": transient}
			if d.Structured == nil {
				p["structured"] = wire.NotesOutput{}
			}
			return p, nil
		})
		if err != nil {
			return reconcileError(err)
		}
		if f.finished() {
			return f.success()
		}
	}
	return queue.Fail(cause)
}

// Reconcile errors preserve the original terminal intent until the external
// document is updated, fenced, or found already complete.
func reconcileError(err error) queue.Outcome {
	fault, ok := errors.AsType[*wire.Fault](err)
	if !ok {
		return wire.Outcome(err)
	}
	switch fault.Result {
	case wire.Fenced, wire.Yielded:
		return fault.Outcome()
	case wire.Succeeded, wire.Transient, wire.Deterministic, wire.Dropped:
		return queue.Retry(fault.Cause, fault.Delay)
	}
	return queue.Retry(fault.Cause, fault.Delay)
}

// accountCheck returns what the queue's preflight learned, or the zero check when the
// preflight did not run for this claim.
func accountCheck(r *queue.Run) wire.AccountCheck {
	check, ok := r.Preflight.(wire.AccountCheck)
	if !ok {
		return wire.AccountCheck{}
	}
	return check
}
