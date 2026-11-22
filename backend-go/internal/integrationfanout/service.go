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

// Budget describes the current guarded delivery attempt.
type Budget struct {
	Number     int
	ClaimToken int64
	Final      bool
}

// Deliver visits every eligible destination even when an earlier receiver asks for
// a retry. Use one canonical finalization job per conversation revision. The guard
// serializes fanout with takeovers and tenant erase, and every receipt write checks
// the account fence again. Consume the report even when a retry is requested.
func (s Service) Deliver(ctx context.Context, run *queue.Run, event Event, targets []Target) (Report, error) {
	destinations, ids, err := planDelivery(event, targets)
	if err != nil || len(ids) == 0 {
		return Report{}, err
	}
	job := run.Job()
	budget := Budget{Number: job.Attempts, ClaimToken: job.Token, Final: run.FinalAttempt()}
	var report Report
	err = run.Guard(ctx, func(ctx context.Context, g queue.Guarded) error {
		var deliveryErr error
		report, deliveryErr = s.deliverGuarded(ctx, g, event, destinations, ids, budget)
		return deliveryErr
	})
	return report, err
}

// DeliverGuarded uses the caller's active guard without acquiring a second
// PostgreSQL session or reopening the lease.
func (s Service) DeliverGuarded(ctx context.Context, g queue.Guarded, event Event, targets []Target, budget Budget) (Report, error) {
	destinations, ids, err := planDelivery(event, targets)
	if err != nil || len(ids) == 0 {
		return Report{}, err
	}
	return s.deliverGuarded(ctx, g, event, destinations, ids, budget)
}

func planDelivery(event Event, targets []Target) ([]destination, []Receipt, error) {
	if event.Locked || event.Discarded {
		return nil, nil, nil
	}
	if event.ConversationID == "" || event.Revision <= 0 {
		return nil, nil, queue.Classify(errors.New("integration: invalid conversation revision"), queue.Fail(CauseInvalid))
	}
	if event.FanoutKey != "" && event.FanoutKey != pythonFanoutKey(event.ConversationID, event.Revision) {
		return nil, nil, queue.Classify(errors.New("integration: invalid persisted fanout key"), queue.Fail(CauseInvalid))
	}
	destinations, ids := selectDestinations(event, targets)
	return destinations, ids, nil
}

func (s Service) deliverGuarded(ctx context.Context, g queue.Guarded, event Event, destinations []destination, ids []Receipt, budget Budget) (Report, error) {
	if err := g.Err(); err != nil {
		return Report{}, err
	}
	settled, err := s.Receipts.Read(ctx, g, ids)
	if err != nil {
		return Report{}, err
	}
	return s.deliverPending(ctx, g, event, destinations, settled, budget)
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

func (s Service) deliverPending(ctx context.Context, g queue.Guarded, event Event,
	destinations []destination, settled map[Receipt]Disposition, budget Budget,
) (Report, error) {
	var report Report
	var retry bool
	var delay time.Duration
	refreshFence := false
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
		attempt, err := s.send(ctx, g, event, d, budget)
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

func (s Service) send(ctx context.Context, g queue.Guarded, event Event, d destination, budget Budget) (Attempt, error) {
	key := deliveryKey(g, event, d.target.AppID)
	result, err := s.Sender.Send(ctx, g, Delivery{
		AppID: d.target.AppID, URL: d.target.URL, Body: d.target.Body, Headers: d.target.Headers, IdempotencyKey: key,
	})
	if err != nil {
		return Attempt{}, err
	}
	if budget.Final && result.Disposition == Transient {
		result.Disposition = Rejected
	}
	return Attempt{
		Receipt: d.id, Result: result, Number: budget.Number, ClaimToken: budget.ClaimToken, IdempotencyKey: key,
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
