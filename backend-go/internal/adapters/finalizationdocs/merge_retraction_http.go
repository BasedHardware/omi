package finalizationdocs

import (
	"context"
	"errors"
	"net/http"
	"slices"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const mergeRetractionPath = "/v1/conversation-finalization-jobs/retract-merge-source"

var errMergeRetraction = errors.New("finalization: authoritative merge retraction unavailable")

// HTTPMergeRetraction delegates to the canonical retraction service. The
// receiver resolves the source ordinal and independently validates the lease.
type HTTPMergeRetraction struct {
	Client *httpx.Client
	Bearer func(context.Context) (string, error)
}

type mergeRetractionRequest struct {
	Job         string `json:"job_id"`
	Generation  int64  `json:"dispatch_generation"`
	Epoch       int64  `json:"lease_epoch"`
	SourceIndex int    `json:"source_index"`
}

type mergeRetractionResponse struct {
	Status string `json:"status"`
}

// Retract succeeds only after the canonical receiver acknowledges retraction.
func (r HTTPMergeRetraction) Retract(ctx context.Context, a queue.Admitting, claim finalization.MergeJob, source string) error {
	if err := a.Err(); err != nil {
		return err
	}
	index := slices.Index(claim.Sources, source)
	if a.Tenant() != claim.Owner || claim.ID == "" || claim.Generation <= 0 || claim.Epoch <= 0 || index < 0 ||
		r.Client == nil || r.Bearer == nil {
		return finalization.ErrInvalid
	}
	token, err := r.Bearer(ctx)
	if err != nil || token == "" {
		return errMergeRetraction
	}
	if err := a.Err(); err != nil {
		return err
	}
	var response mergeRetractionResponse
	fault := r.Client.Do(ctx, httpx.Request{
		Method: http.MethodPost, Path: mergeRetractionPath,
		Header: map[string]string{"Authorization": "Bearer " + token},
		Body:   mergeRetractionRequest{Job: claim.ID, Generation: claim.Generation, Epoch: claim.Epoch, SourceIndex: index},
		Out:    &response,
	})
	if fault != nil || response.Status != "retracted" {
		return errMergeRetraction
	}
	return a.Err()
}
