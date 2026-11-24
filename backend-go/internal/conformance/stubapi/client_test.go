package stubapi

import (
	"net/http"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestFaultClassification(t *testing.T) {
	cases := []struct {
		vendor Vendor
		status int
		code   string
		result Result
		cause  queue.Cause
	}{
		{LLMVendor, 429, "injected_fault", Transient, CauseRateLimited},
		{LLMVendor, 503, "injected_fault", Transient, CauseVendorUnavailable},
		{LLMVendor, 401, "invalid_vendor_key", Deterministic, CauseVendorRejected},
		{AppVendor, 429, "injected_fault", Dropped, CauseIntegrationDropped},
		{AppVendor, 409, "fenced", Fenced, CauseConversationFenced},
		{AppVendor, 409, "record_owner_contention", Yielded, CauseRecordOwnerContention},
		{DocumentVendor, 409, "episode_notes_pending", Yielded, CauseEpisodeNotesPending},
		{DocumentVendor, 409, "version_conflict", Deterministic, CauseVersionConflict},
		{DocumentVendor, 409, "account_deleting", Yielded, CauseAccountDeleting},
		{DocumentVendor, 410, "tombstone", Fenced, CauseConversationFenced},
	}
	for _, c := range cases {
		delay := 4 * time.Second
		f := classify(c.vendor, &httpx.Fault{Kind: httpx.FaultStatus, Status: c.status, Code: c.code, RetryAfter: delay})
		if f.Result != c.result || f.Cause != c.cause || f.Delay != delay {
			t.Errorf("%+v: %+v", c, f)
		}
	}
}

func TestRetryAfter(t *testing.T) {
	now := time.Date(2026, 11, 19, 11, 0, 0, 0, time.UTC)
	for _, tc := range []struct {
		value string
		delay time.Duration
	}{
		{"17", 17 * time.Second},
		{now.Add(15 * time.Second).Format(http.TimeFormat), 15 * time.Second},
		{now.Add(-15 * time.Second).Format(http.TimeFormat), 0},
		{"garbage", 0},
		{"-15", 0},
	} {
		if got := httpx.RetryAfter(tc.value, now); got != tc.delay {
			t.Errorf("%q: got %v, want %v", tc.value, got, tc.delay)
		}
	}
}
