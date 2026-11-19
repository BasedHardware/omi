package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgconn"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
	"github.com/BasedHardware/omi/backend-go/internal/queue/queuetest"
)

type markerReaderFunc func(context.Context, string) (map[string]any, error)

func (f markerReaderFunc) ReadDeletionMarker(ctx context.Context, owner string) (map[string]any, error) {
	return f(ctx, owner)
}

func TestEraseRequiresAuthenticatedArmedGenerationAndCommit(t *testing.T) {
	t.Parallel()
	claim := strings.Repeat("b", 64)
	for _, tc := range []struct {
		name, token, status, jobID string
		markerErr, eraseErr        error
		want                       int
		calls                      int
	}{
		{"wrong identity", "bad", "running", "job", nil, nil, http.StatusUnauthorized, 0},
		{"grace pending", "trusted", "pending_deletion", "job", nil, nil, http.StatusConflict, 0},
		{"stale generation", "trusted", "running", "old", nil, nil, http.StatusConflict, 0},
		{"uncommitted erase", "trusted", "running", "job", nil, context.DeadlineExceeded, http.StatusServiceUnavailable, 1},
		{"Firestore unavailable", "trusted", "running", "job",
			&docstore.CallError{Kind: docstore.KindTransient, Code: "Unavailable"}, nil, http.StatusServiceUnavailable, 0},
		{"Firestore permission denied", "trusted", "running", "job",
			&docstore.CallError{Kind: docstore.KindRejected, Code: "PermissionDenied"}, nil, http.StatusConflict, 0},
		{"Postgres connection refused", "trusted", "running", "job", nil,
			syscall.ECONNREFUSED, http.StatusServiceUnavailable, 1},
		{"Postgres permission denied", "trusted", "running", "job", nil,
			&pgconn.PgError{Code: "42501"}, http.StatusConflict, 1},
		{"committed erase", "trusted", "running", "job", nil, nil, http.StatusOK, 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			calls := 0
			endpoint := eraseEndpoint{
				authorize: func(_ context.Context, token string) error {
					if token != "trusted" {
						return errors.New("cannot authenticate")
					}
					return nil
				},
				markers: markerReaderFunc(func(_ context.Context, owner string) (map[string]any, error) {
					if owner != "test-tenant" {
						t.Fatalf("marker read for %q", owner)
					}
					if tc.markerErr != nil {
						return nil, tc.markerErr
					}
					return map[string]any{
						"wipe_status": tc.status, "wipe_job_id": tc.jobID,
						"go_queue_erase_claim": claim, "go_queue_erase_armed_at": time.Unix(1, 0),
						"go_queue_erase_claim_expires_at": time.Now().Add(time.Second),
					}, nil
				}),
				erase: func(_ context.Context, owner string) error {
					calls++
					if owner != "test-tenant" {
						t.Fatalf("erase for %q", owner)
					}
					return tc.eraseErr
				},
				report: func(error) {},
			}
			body := `{"tenant":"test-tenant","wipe_job_id":"job","claim":"` + claim + `"}`
			req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, erasePath, strings.NewReader(body))
			req.Header.Set("Authorization", "Bearer "+tc.token)
			rec := httptest.NewRecorder()
			endpoint.routes().ServeHTTP(rec, req)
			if rec.Code != tc.want || calls != tc.calls {
				t.Fatalf("status and calls = %d/%d, want %d/%d", rec.Code, calls, tc.want, tc.calls)
			}
			if tc.want == http.StatusOK && !strings.Contains(rec.Body.String(), `"wipe_job_id":"job","claim":"`+claim) {
				t.Fatal("successful erase must return a receipt for the requesting generation and claim")
			}
		})
	}
}

func TestEraseFailureStatusRejectsMixedConnectionOutcomes(t *testing.T) {
	t.Parallel()
	unavailable := &pgconn.PgError{Code: "57P03"}
	denied := &pgconn.PgError{Code: "42501"}
	for _, err := range []error{errors.Join(unavailable, denied), errors.Join(denied, unavailable)} {
		if got := eraseFailureStatus(fmt.Errorf("pool: %w", err)); got != http.StatusConflict {
			t.Errorf("joined permission denial got HTTP %d", got)
		}
	}
	if got := eraseFailureStatus(errors.Join(unavailable, syscall.ECONNREFUSED)); got != http.StatusServiceUnavailable {
		t.Errorf("joined transient failures got HTTP %d", got)
	}
	if got := eraseFailureStatus(fmt.Errorf("read commit acknowledgement: %w", io.ErrUnexpectedEOF)); got != http.StatusServiceUnavailable {
		t.Errorf("lost acknowledgement got HTTP %d", got)
	}
}

func TestEraseGrantRejectsExpiredOrStaleClaim(t *testing.T) {
	t.Parallel()
	now := time.Now()
	req := eraseRequest{Tenant: "tenant", JobID: "job", Claim: strings.Repeat("b", 64)}
	marker := map[string]any{
		"wipe_status": "running", "wipe_job_id": req.JobID, "go_queue_erase_claim": req.Claim,
		"go_queue_erase_armed_at": now.Add(-time.Minute), "go_queue_erase_claim_expires_at": now,
	}
	if _, ok := eraseGrant(marker, req, now); ok {
		t.Fatal("expired grant was accepted")
	}
	marker["go_queue_erase_claim_expires_at"] = now.Add(time.Second)
	marker["go_queue_erase_claim"] = strings.Repeat("a", 64)
	if _, ok := eraseGrant(marker, req, now); ok {
		t.Fatal("stale claim was accepted")
	}
}

func TestEraseEndpointCommitsTenantFence(t *testing.T) {
	t.Parallel()
	h := queuetest.Open(t, queuetest.Policy(), testKind())
	eraser, ok := any(h.Store).(queueOnlyEraser)
	if !ok {
		t.Skip("requires Lane B queue routine (#25825)")
	}
	fs := docstoretest.Open(t)
	reader, ok := any(fs.Store).(deletionMarkerReader)
	if !ok {
		t.Skip("requires Lane B marker reader (#25827)")
	}

	claim := strings.Repeat("c", 64)
	fs.Mark(t, "tenant", map[string]any{
		"wipe_status": "running", "wipe_job_id": "job", "go_queue_erase_claim": claim,
		"go_queue_erase_armed_at": time.Now(), "go_queue_erase_claim_expires_at": time.Now().Add(time.Minute),
	})
	initial := queue.NewJob{Key: "one", Tenant: "tenant", Kind: "example", Format: 1, Step: "call"}
	if _, err := h.Store.Enqueue(t.Context(), initial); err != nil {
		t.Fatal(err)
	}
	endpoint := eraseEndpoint{
		authorize: func(context.Context, string) error { return nil },
		markers:   reader,
		erase:     eraser.EraseQueue,
		report:    func(err error) { t.Error(err) },
	}
	body := `{"tenant":"tenant","wipe_job_id":"job","claim":"` + claim + `"}`
	for range 2 {
		req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, erasePath, strings.NewReader(body))
		req.Header.Set("Authorization", "Bearer test")
		rec := httptest.NewRecorder()
		endpoint.routes().ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("erase HTTP status = %d", rec.Code)
		}
	}
	if _, err := h.Store.Get(t.Context(), initial.Key); !errors.Is(err, queue.ErrAbsent) {
		t.Fatalf("existing queue job was not purged: %v", err)
	}
	initial.Key = "late"
	if _, err := h.Store.Enqueue(t.Context(), initial); !errors.Is(err, queue.ErrErased) {
		t.Fatalf("late admission was not fenced: %v", err)
	}
}
