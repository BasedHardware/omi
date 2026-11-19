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

// Result captures the disposition and any backoff requested by a transient response.
type Result struct {
	Disposition Disposition
	RetryAfter  time.Duration
}

// Delivery is an outbound request. Body is the integration-safe JSON projection;
// credentials and any optional signing headers are supplied by the caller in memory.
type Delivery struct {
	URL            string
	Body           []byte
	Headers        map[string]string
	IdempotencyKey string
}

// Sender sends one external request with the worker's guarded lease.
type Sender interface {
	Send(ctx context.Context, g queue.Guarded, d Delivery) (Result, error)
}

// Receipts stores terminal dispositions. Read also checks the authoritative owner
// deletion marker, including for a receipt that does not yet exist.
type Receipts interface {
	Read(ctx context.Context, g queue.Guarded, id Receipt) (Disposition, error)
	Record(ctx context.Context, g queue.Guarded, id Receipt, disposition Disposition) error
}
