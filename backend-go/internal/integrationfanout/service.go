package integrationfanout

import (
	"context"
	"errors"
	"strconv"
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

// Event describes a claimed conversation revision. FanoutKey is the persisted
// Python key for this conversation revision, when available.
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
	AppID        string
	Enabled      bool
	Created      bool
	Disabled     bool
	OwnedByOwner bool
	URL          string
	Body         []byte
	Headers      map[string]string
}

// Service dispatches the callback destinations supplied by finalization.
type Service struct {
	Sender   Sender
	Receipts Receipts
}

type destination struct {
	id     Receipt
	target Target
}

// Deliver visits every eligible destination even when an earlier receiver asks for
// a retry. Use one canonical finalization job per conversation revision. The guard
// serializes fanout with takeovers and tenant erase, and every receipt write checks
// the account fence again. Consume the report even when a retry is requested.
func (s Service) Deliver(ctx context.Context, run *queue.Run, event Event, targets []Target) (Report, error) {
	if event.Locked || event.Discarded {
		return Report{}, nil
	}
	if event.ConversationID == "" || event.Revision <= 0 {
		return Report{}, queue.Classify(errors.New("integration: invalid conversation revision"), queue.Fail(CauseInvalid))
	}
	if event.FanoutKey != "" && event.FanoutKey != pythonFanoutKey(event.ConversationID, event.Revision) {
		return Report{}, queue.Classify(errors.New("integration: invalid persisted fanout key"), queue.Fail(CauseInvalid))
	}
	destinations, ids := selectDestinations(event, targets)
	if len(ids) == 0 {
		return Report{}, nil
	}
	var report Report
	err := run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		settled, err := s.Receipts.Read(ctx, g, ids)
		if err != nil {
			return err
		}
		report, err = s.deliverPending(ctx, g, run, event, destinations, settled)
		return err
	})
	return report, err
}

func eligible(target Target) bool {
	return target.Enabled && target.Created && !target.Disabled && target.URL != ""
}

func selectDestinations(event Event, targets []Target) ([]destination, []Receipt) {
	seen := make(map[string]bool)
	var destinations []destination
	var ids []Receipt
	for _, target := range targets {
		if !eligible(target) || seen[target.AppID] {
			continue
		}
		seen[target.AppID] = true
		id := Receipt{ConversationID: event.ConversationID, Revision: event.Revision, AppID: target.AppID}
		destinations = append(destinations, destination{id: id, target: target})
		ids = append(ids, id)
	}
	return destinations, ids
}

func (s Service) deliverPending(ctx context.Context, g queue.Guarded, run *queue.Run, event Event,
	destinations []destination, settled map[Receipt]Disposition,
) (Report, error) {
	var report Report
	var retry bool
	var delay time.Duration
	refreshFence := false
	claim, final := run.Job(), run.FinalAttempt()
	for _, d := range destinations {
		if prior := settled[d.id]; prior != 0 {
			report.Dropped = report.Dropped || prior == Rejected
			continue
		}
		if refreshFence {
			// A transient attempt has no receipt write to recheck the deletion marker.
			if _, err := s.Receipts.Read(ctx, g, nil); err != nil {
				return report, err
			}
		}
		attempt, err := s.send(ctx, g, event, d, claim, final)
		if err != nil {
			return report, err
		}
		report.Attempts = append(report.Attempts, attempt)
		refreshFence = attempt.Disposition == Transient
		if refreshFence {
			retry = true
			delay = max(delay, attempt.RetryAfter)
			continue
		}
		report.Dropped = report.Dropped || attempt.Disposition == Rejected
		if err := s.Receipts.Record(ctx, g, d.id, attempt.Disposition); err != nil {
			return report, err
		}
	}
	if retry {
		return report, queue.Classify(errors.New("integration: delivery requires retry"), queue.Retry(CauseRetry, delay))
	}
	return report, nil
}

func (s Service) send(ctx context.Context, g queue.Guarded, event Event, d destination, claim queue.Job, final bool) (Attempt, error) {
	key := deliveryKey(g, event, d.target.AppID)
	result, err := s.Sender.Send(ctx, g, Delivery{
		AppID: d.target.AppID, URL: d.target.URL, Body: d.target.Body, Headers: d.target.Headers, IdempotencyKey: key,
	})
	if err != nil {
		return Attempt{}, err
	}
	if final && result.Disposition == Transient {
		result.Disposition = Rejected
	}
	return Attempt{
		Receipt: d.id, Result: result, Number: claim.Attempts, ClaimToken: claim.Token, IdempotencyKey: key,
		RecordUsage: result.Disposition == Accepted && d.target.AppID != "" && !d.target.OwnedByOwner,
		DeadLetter:  result.Disposition == Rejected && d.target.AppID == "",
	}, nil
}

func deliveryKey(g queue.Guarded, event Event, app string) string {
	if event.FanoutKey != "" {
		return event.FanoutKey
	}
	return g.Operation("integration:" + app)
}

func pythonFanoutKey(conversationID string, revision int64) string {
	return "conversation:" + conversationID + ":finalization:" + strconv.FormatInt(revision, 10)
}
