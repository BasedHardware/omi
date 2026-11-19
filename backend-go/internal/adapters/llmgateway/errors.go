package llmgateway

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Closed outcomes the wiring must register in the finalization kind's declaration.
const (
	CauseExpired       queue.Cause = "llm_gateway_replay_expired"
	CauseServiceAuth   queue.Cause = "llm_gateway_service_auth"
	CauseIndeterminate queue.Cause = "llm_gateway_indeterminate"
	CauseTransient     queue.Cause = "llm_gateway_transient"
	CauseRejected      queue.Cause = "llm_gateway_rejected"
	CauseQuota         queue.Cause = "llm_gateway_quota"
	CauseBYOK          queue.Cause = "llm_gateway_byok"
	CauseBYOKQuota     queue.Cause = "llm_gateway_byok_quota"
	CauseBYOKRateLimit queue.Cause = "llm_gateway_byok_rate_limit"
)

// Causes lists all gateway causes for the kind's declaration.
func Causes() []queue.Cause {
	return []queue.Cause{CauseTransient, CauseRejected, CauseQuota, CauseBYOK, CauseBYOKQuota, CauseBYOKRateLimit, CauseIndeterminate, CauseExpired, CauseServiceAuth}
}

// CallError reports a closed cause and HTTP status. It contains no gateway response text.
type CallError struct {
	Cause  queue.Cause
	Status int
}

func (e *CallError) Error() string {
	return fmt.Sprintf("llmgateway: %s (status %d)", e.Cause, e.Status)
}

func classify(cause queue.Cause, status int, delay time.Duration) error {
	err := &CallError{Cause: cause, Status: status}
	if cause == CauseTransient || cause == CauseQuota || cause == CauseBYOKRateLimit || cause == CauseServiceAuth {
		return queue.Classify(err, queue.Retry(cause, delay))
	}
	return queue.Classify(err, queue.Fail(cause))
}

const maxErrorEnvelopeBytes = 64 << 10

type errorEnvelope struct {
	Error *struct {
		Code         string `json:"code"`
		FailureClass string `json:"failure_class"`
	} `json:"error"`
}

func readCause(resp *http.Response) (queue.Cause, string) {
	var payload errorEnvelope
	if err := json.NewDecoder(io.LimitReader(resp.Body, maxErrorEnvelopeBytes)).Decode(&payload); err != nil || payload.Error == nil {
		if resp.StatusCode == http.StatusNotFound {
			// An older replica returns a bare 404 for the keyed route.
			return CauseTransient, ""
		}
		return responseCause(resp.StatusCode, "", ""), ""
	}
	code := payload.Error.Code
	return responseCause(resp.StatusCode, code, payload.Error.FailureClass), code
}

func responseCause(status int, code, failureClass string) queue.Cause {
	switch code {
	case "idempotency_pending":
		return CauseTransient
	case "idempotency_indeterminate", "idempotency_expired", "idempotency_not_found":
		return CauseIndeterminate
	case "invalid_route_config", "idempotency_owner_unavailable":
		return CauseRejected
	}
	switch failureClass {
	case "byok_auth", "byok_unsupported_provider", "missing_byok_key":
		return CauseBYOK
	case "byok_quota":
		return CauseBYOKQuota
	case "byok_rate_limit":
		return CauseBYOKRateLimit
	case "timeout_before_output", "reserved_capacity_unavailable", "provider_5xx_omi_paid":
		return CauseTransient
	case "provider_429_omi_paid":
		return CauseQuota
	case "provider_invalid_request", "capability_mismatch", "invalid_config":
		return CauseRejected
	}
	switch {
	case status == http.StatusUnauthorized || status == http.StatusForbidden:
		return CauseServiceAuth
	case status == http.StatusTooManyRequests:
		return CauseQuota
	case status == http.StatusRequestTimeout || status >= http.StatusInternalServerError:
		return CauseTransient
	default:
		return CauseRejected
	}
}
