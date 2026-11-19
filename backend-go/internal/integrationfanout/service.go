package integrationfanout

import (
	"context"
	"errors"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	// CauseRetry is a delivery with an ambiguous or transient result.
	CauseRetry queue.Cause = "integration_retry"
	// CauseDropped is a delivery rejected by its destination or out of retry budget.
	CauseDropped queue.Cause = "integration_dropped"
	// CauseDeleting holds an owner with an active deletion marker.
	CauseDeleting queue.Cause = "integration_owner_deleting"
	// CauseStore is a failure to read or persist a delivery disposition.
	CauseStore queue.Cause = "integration_receipt_store"
	// CauseInvalid is an invalid event or receipt.
	CauseInvalid queue.Cause = "integration_invalid"
)

// Causes returns the causes the calling finalization kind must declare.
func Causes() []queue.Cause {
	return []queue.Cause{CauseRetry, CauseDropped, CauseDeleting, CauseStore, CauseInvalid}
}

// Event describes a claimed conversation revision. FanoutKey is the persisted key
// shared with Python when supplied. The service derives a key from the job otherwise.
type Event struct {
	ConversationID string
	Revision       int64
	FanoutKey      string
	Locked         bool
	Discarded      bool
}

// Target is a destination resolved for this owner on the current attempt. Enabled
// incorporates the owner's app or webhook setting. Created is the event trigger,
// and Disabled covers operational disablement independently of the owner's setting.
// An empty AppID identifies the owner's developer webhook.
type Target struct {
	AppID    string
	Enabled  bool
	Created  bool
	Disabled bool
	URL      string
	Body     []byte
	Headers  map[string]string
}

// Service dispatches the callback destinations supplied by finalization.
type Service struct {
	Sender   Sender
	Receipts Receipts
}

// Deliver visits every eligible destination even when an earlier receiver asks for a
// retry. The caller must use one canonical finalization job per conversation revision.
// Its guard serializes sends and receipt commits with takeovers and tenant erase.
func (s Service) Deliver(ctx context.Context, run *queue.Run, event Event, targets []Target) (bool, error) {
	if event.Locked || event.Discarded {
		return false, nil
	}
	if event.ConversationID == "" || event.Revision < 0 {
		return false, queue.Classify(errors.New("integration: invalid conversation revision"), queue.Fail(CauseInvalid))
	}
	var dropped, retry bool
	var delay time.Duration
	seen := make(map[string]bool)
	for _, target := range targets {
		if !eligible(target) || seen[target.AppID] {
			continue
		}
		seen[target.AppID] = true
		var result Result
		err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
			var err error
			result, err = s.deliverOne(ctx, g, event, target, run.FinalAttempt())
			return err
		})
		if err != nil {
			return dropped, err
		}
		dropped = dropped || result.Disposition == Rejected
		retry = retry || result.Disposition == Transient
		delay = max(delay, result.RetryAfter)
	}
	if retry {
		return dropped, queue.Classify(errors.New("integration: delivery requires retry"), queue.Retry(CauseRetry, delay))
	}
	return dropped, nil
}

func eligible(target Target) bool {
	return target.Enabled && target.Created && !target.Disabled && target.URL != ""
}

func (s Service) deliverOne(ctx context.Context, g queue.Guarded, event Event, target Target, final bool) (Result, error) {
	id := Receipt{ConversationID: event.ConversationID, Revision: event.Revision, AppID: target.AppID}
	previous, err := s.Receipts.Read(ctx, g, id)
	if err != nil || previous != 0 {
		return Result{Disposition: previous}, err
	}
	key := event.FanoutKey
	if key == "" {
		key = g.Operation("integration:" + target.AppID)
	}
	result, err := s.Sender.Send(ctx, g, Delivery{
		URL: target.URL, Body: target.Body, Headers: target.Headers, IdempotencyKey: key,
	})
	if err != nil {
		return Result{}, err
	}
	if result.Disposition == Transient {
		if !final {
			return result, nil
		}
		result = Result{Disposition: Rejected}
	}
	return result, s.Receipts.Record(ctx, g, id, result.Disposition)
}
