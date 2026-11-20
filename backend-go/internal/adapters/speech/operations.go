package speech

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// ErrNotCommitted reports that the operation has no recoverable result.
var ErrNotCommitted = errors.New("speech: no committed transcription")

const (
	operationCollection = "speech_modulate_operations"
	statePending        = "pending"
	stateRetryable      = "retryable"
	stateRejected       = "rejected"
	stateComplete       = "complete"
)

// Queue causes are closed and carry no audio, credentials or remote messages.
const (
	CauseOwnerKey          queue.Cause = "speech_owner_key"
	CauseOwnerQuota        queue.Cause = "speech_owner_quota"
	CauseManagedKey        queue.Cause = "speech_managed_key"
	CauseProviderBudget    queue.Cause = "speech_provider_budget"
	CauseProviderRateLimit queue.Cause = "speech_provider_rate_limit"
	CauseInput             queue.Cause = "speech_input"
	CauseUnresolved        queue.Cause = "speech_unresolved"
	CauseInvalidReply      queue.Cause = "speech_invalid_reply"
	CauseStoreUnavailable  queue.Cause = "speech_store_unavailable"
	CauseStoreRejected     queue.Cause = "speech_store_rejected"
	CauseOwnerDeleting     queue.Cause = "speech_owner_deleting"
)

// Causes lists the causes for a kind that uses this adapter.
func Causes() []queue.Cause {
	return []queue.Cause{CauseOwnerKey, CauseOwnerQuota, CauseManagedKey, CauseProviderBudget, CauseProviderRateLimit,
		CauseInput, CauseUnresolved, CauseInvalidReply, CauseStoreUnavailable, CauseStoreRejected, CauseOwnerDeleting}
}

type operationRecord struct {
	State   string `firestore:"state"`
	Attempt int64  `firestore:"attempt"`
	Reply   string `firestore:"reply,omitempty"`
	Cause   string `firestore:"cause,omitempty"`
}

type reservation struct {
	ref     docstore.Ref
	attempt int64
}

func (rec operationRecord) canReserve() bool {
	return rec.State == "" || rec.State == stateRetryable
}

type savedReply struct {
	Body     json.RawMessage `json:"body"`
	Language string          `json:"language"`
}

func operationRef(g queue.Guarded, step string) (docstore.Ref, error) {
	if err := g.Err(); err != nil {
		return docstore.Ref{}, err
	}
	if step == "" {
		return docstore.Ref{}, failure(CauseInput)
	}
	ref, err := docstore.Doc("users", g.Tenant(), operationCollection, g.Operation(step))
	if err != nil {
		return docstore.Ref{}, failure(CauseInput)
	}
	return ref, nil
}

func (m *Modulate) read(ctx context.Context, g queue.Guarded, ref docstore.Ref) (operationRecord, error) {
	var rec operationRecord
	err := m.docs.Fenced(ctx, g, g.Tenant(), func(tx *docstore.Tx) error {
		rec = operationRecord{}
		_, err := tx.Get(ref, &rec)
		return err
	})
	return rec, storeFailure(err)
}

// Atomically claim an absent or retryable operation. An empty result state with
// no error authorizes one POST for that attempt.
func (m *Modulate) reserve(ctx context.Context, g queue.Guarded, ref docstore.Ref) (operationRecord, error) {
	var rec operationRecord
	err := m.docs.Fenced(ctx, g, g.Tenant(), func(tx *docstore.Tx) error {
		rec = operationRecord{}
		found, err := tx.Get(ref, &rec)
		if err != nil {
			return err
		}
		if !found {
			rec.Attempt = 1
			return tx.Create(ref, operationRecord{State: statePending, Attempt: rec.Attempt})
		}
		if rec.State == "" {
			rec.State = statePending
		}
		if rec.State != stateRetryable {
			return nil
		}
		rec = operationRecord{Attempt: rec.Attempt + 1}
		return tx.Update(ref, map[string]any{"state": statePending, "attempt": rec.Attempt})
	})
	return rec, storeFailure(err)
}

func (m *Modulate) finish(ctx context.Context, g queue.Guarded, claim reservation, rec operationRecord) error {
	err := m.docs.Fenced(ctx, g, g.Tenant(), func(tx *docstore.Tx) error {
		var current operationRecord
		found, err := tx.Get(claim.ref, &current)
		if err != nil {
			return err
		}
		if !found || current.State != statePending || current.Attempt != claim.attempt {
			return docstore.ErrMissing
		}
		return tx.Update(claim.ref, map[string]any{
			"state": rec.State, "reply": rec.Reply, "cause": rec.Cause,
		})
	})
	return storeFailure(err)
}

func (m *Modulate) reject(ctx context.Context, g queue.Guarded, claim reservation, cause queue.Cause) error {
	if cause == CauseProviderRateLimit {
		if err := m.finish(ctx, g, claim, operationRecord{State: stateRetryable}); err != nil {
			return err
		}
		return queue.Classify(errors.New(string(cause)), queue.Retry(cause, 0))
	}
	if cause != CauseUnresolved {
		if err := m.finish(ctx, g, claim, operationRecord{State: stateRejected, Cause: string(cause)}); err != nil {
			return err
		}
	}
	return failure(cause)
}

func (m *Modulate) result(owner string, rec operationRecord) (Transcript, error) {
	switch rec.State {
	case statePending:
		return Transcript{}, failure(CauseUnresolved)
	case stateRejected:
		switch rec.Cause {
		case string(CauseOwnerKey), string(CauseOwnerQuota), string(CauseManagedKey), string(CauseProviderBudget),
			string(CauseProviderRateLimit), string(CauseInput), string(CauseInvalidReply):
			return Transcript{}, failure(queue.Cause(rec.Cause))
		}
	case stateComplete:
		payload, err := m.codec.Open(owner, rec.Reply)
		var saved savedReply
		if err != nil || json.Unmarshal(payload, &saved) != nil {
			return Transcript{}, failure(CauseStoreRejected)
		}
		reply, err := parseReply(saved.Body, saved.Language)
		if err != nil {
			return Transcript{}, failure(CauseStoreRejected)
		}
		return reply, nil
	}
	return Transcript{}, failure(CauseStoreRejected)
}

func failure(cause queue.Cause) error {
	return queue.Classify(errors.New(string(cause)), queue.Fail(cause))
}

func storeFailure(err error) error {
	if err == nil || errors.Is(err, queue.ErrLease) || errors.Is(err, context.Canceled) {
		return err
	}
	if errors.Is(err, docstore.ErrOwnerDeleting) {
		return queue.Classify(err, queue.Hold(CauseOwnerDeleting, time.Minute))
	}
	fault, typed := errors.AsType[*docstore.CallError](err)
	if errors.Is(err, docstore.ErrExists) || (typed && fault.Kind == docstore.KindTransient) {
		return queue.Classify(err, queue.Retry(CauseStoreUnavailable, 0))
	}
	return failure(CauseStoreRejected)
}
