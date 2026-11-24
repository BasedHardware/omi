// Package integrationfanout coordinates third-party deliveries for a finalized conversation.
package integrationfanout

import (
	"context"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Receipt identifies one destination for one conversation revision. The empty AppID
// identifies the owner's developer webhook. The guard supplies the owner.
type Receipt struct {
	ConversationID string
	Revision       int64
	AppID          string
}

// Disposition is the result of one sender call. A transport that cannot determine
// whether the request was accepted reports Transient.
type Disposition uint8

// Delivery dispositions.
const (
	Accepted Disposition = iota + 1
	Rejected
	Transient
)

// Failure describes why a delivery did not receive a 2xx.
type Failure uint8

// Delivery failure classes. A successful Result has no failure.
const (
	HTTPFailure Failure = iota + 1
	TransportFailure
	Timeout
	InvalidDestination
)

// Result captures the response status, retry delay and bounded app message. Status is
// zero for transport failures. Invalid developer destinations have a synthetic 400.
// Message is untrusted and stays out of the job row.
type Result struct {
	Disposition Disposition
	Status      int
	Failure     Failure
	RetryAfter  time.Duration
	Message     string
}

// Delivery is an outbound request. Body is the integration-safe JSON projection.
// An empty AppID identifies the developer webhook. Any optional signing headers
// are supplied by the caller in memory.
type Delivery struct {
	AppID          string
	URL            string
	Body           []byte
	Headers        map[string]string
	IdempotencyKey string
}

// Attempt reports one delivery to the finalization caller. Receipt and ClaimToken
// identify the attempt even if the queue refunds its attempt number. RecordUsage
// selects marketplace usage history on success.
// DeadLetter selects terminal developer webhook failures. The caller can match the
// receipt to the original target for DLQ input without persisting it in the queue.
type Attempt struct {
	Receipt
	Result
	Number         int
	ClaimToken     int64
	IdempotencyKey string
	RecordUsage    bool
	DeadLetter     bool
}

// Report includes attempts made in this call, including when Deliver returns an
// error. Previously settled receipts suppress delivery. A settled receipt
// contributes to Dropped only if it recorded a rejection.
type Report struct {
	Dropped  bool
	Attempts []Attempt
}

// Sender sends one external request with the worker's guarded lease.
type Sender interface {
	Send(ctx context.Context, g queue.Guarded, d Delivery) (Result, error)
}

// Receipts stores terminal dispositions. Read checks the authoritative owner
// deletion marker, including when ids is empty.
type Receipts interface {
	Read(ctx context.Context, g queue.Guarded, ids []Receipt) (map[Receipt]Disposition, error)
	Record(ctx context.Context, g queue.Guarded, id Receipt, disposition Disposition) error
}
