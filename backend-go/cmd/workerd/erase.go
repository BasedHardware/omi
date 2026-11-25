package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"regexp"
	"strings"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
	"google.golang.org/api/idtoken"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const erasePath = "/internal/v1/tenant-erase"

type eraseRequest struct {
	Tenant string `json:"tenant"`
	JobID  string `json:"wipe_job_id"`
	Claim  string `json:"claim"`
}

type eraseReceipt struct {
	JobID string `json:"wipe_job_id"`
	Claim string `json:"claim"`
}

type deletionMarkerReader interface {
	ReadDeletionMarker(context.Context, string) (map[string]any, error)
}

type eraseEndpoint struct {
	authorize func(context.Context, string) error
	markers   deletionMarkerReader
	erase     func(context.Context, string) error
	report    func(error)
}

var (
	wipeJobID = regexp.MustCompile(`^[A-Za-z0-9_-]{1,128}$`)
	claimHash = regexp.MustCompile(`^[a-f0-9]{64}$`)
)

func (e eraseEndpoint) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST "+erasePath, e.handle)
	return mux
}

func (e eraseEndpoint) handle(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 6*time.Second)
	defer cancel()
	token, ok := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
	if !ok || token == "" || e.authorize(ctx, token) != nil {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 2048))
	decoder.DisallowUnknownFields()
	var request eraseRequest
	if err := decoder.Decode(&request); err != nil || !validEraseRequest(request) {
		http.Error(w, "invalid erase request", http.StatusBadRequest)
		return
	}
	if err := decoder.Decode(new(any)); !errors.Is(err, io.EOF) {
		http.Error(w, "invalid erase request", http.StatusBadRequest)
		return
	}
	marker, err := e.markers.ReadDeletionMarker(ctx, request.Tenant)
	if err != nil {
		e.report(err)
		http.Error(w, "marker authority check failed", eraseFailureStatus(err))
		return
	}
	expires, armed := eraseGrant(marker, request, time.Now())
	if !armed {
		http.Error(w, "erase claim rejected", http.StatusConflict)
		return
	}
	ctx, endGrant := context.WithDeadline(ctx, expires)
	defer endGrant()
	if eraseErr := e.erase(ctx, request.Tenant); eraseErr != nil {
		e.report(eraseErr)
		http.Error(w, "erase error", eraseFailureStatus(eraseErr))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	if writeErr := json.NewEncoder(w).Encode(eraseReceipt{JobID: request.JobID, Claim: request.Claim}); writeErr != nil {
		e.report(writeErr)
	}
}

func validEraseRequest(req eraseRequest) bool {
	if req.Tenant == "" || len(req.Tenant) > 512 || strings.TrimSpace(req.Tenant) != req.Tenant ||
		strings.Contains(req.Tenant, "/") || req.Tenant == "." || req.Tenant == ".." {
		return false
	}
	return wipeJobID.MatchString(req.JobID) && claimHash.MatchString(req.Claim)
}

func eraseGrant(marker map[string]any, req eraseRequest, now time.Time) (time.Time, bool) {
	armed, ok := marker["go_queue_erase_armed_at"].(time.Time)
	expires, expiryOK := marker["go_queue_erase_claim_expires_at"].(time.Time)
	return expires, ok && !armed.IsZero() && expiryOK && now.Before(expires) && marker["wipe_status"] == "running" &&
		marker["wipe_job_id"] == req.JobID && marker["go_queue_erase_claim"] == req.Claim
}

func eraseFailureStatus(err error) int {
	_, connecting := errors.AsType[*pgconn.ConnectError](err)
	if transientEraseFailure(err, !connecting) {
		return http.StatusServiceUnavailable
	}
	return http.StatusConflict
}

// A connection can try several addresses. Every outcome must be transient
// before another credential may retry an operation.
func transientEraseFailure(err error, established bool) bool {
	if joined, ok := errors.AsType[interface {
		error
		Unwrap() []error
	}](err); ok {
		for _, cause := range joined.Unwrap() {
			if !transientEraseFailure(cause, established) {
				return false
			}
		}
		return true
	}
	if fault, ok := errors.AsType[*docstore.CallError](err); ok {
		return fault.Kind == docstore.KindTransient
	}
	if fault, ok := errors.AsType[*pgconn.PgError](err); ok {
		switch fault.Code {
		case "08000", "08001", "08003", "08006", "08007", "55P03", "57014", "57P01", "57P02", "57P03", "53300":
			return true
		}
		return false
	}
	if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) ||
		errors.Is(err, syscall.ECONNREFUSED) || errors.Is(err, syscall.ECONNRESET) ||
		errors.Is(err, syscall.EHOSTUNREACH) || errors.Is(err, syscall.ENETUNREACH) ||
		(established && errors.Is(err, io.ErrUnexpectedEOF)) {
		return true
	}
	var network net.Error
	return errors.As(err, &network) && network.Timeout()
}

func authorizeErase(validator *idtoken.Validator, cfg eraseConfig) func(context.Context, string) error {
	return func(ctx context.Context, token string) error {
		payload, err := validator.Validate(ctx, token, cfg.audience)
		if err != nil {
			return errors.New("unverified caller")
		}
		if (payload.Issuer != "https://accounts.google.com" && payload.Issuer != "accounts.google.com") ||
			payload.Subject != cfg.subject {
			return errors.New("unexpected caller identity")
		}
		return nil
	}
}

type queueOnlyEraser interface {
	EraseQueue(context.Context, string) error
}

func openEraseServer(ctx context.Context, cfg config, store *queue.Store, logger *slog.Logger) (*http.Server, func(), error) {
	if cfg.erase.port == 0 {
		return nil, func() {}, nil
	}
	// CLEANUP-NOTE: use direct assignments once Lane B's erase and marker reader land.
	eraser, ok := any(store).(queueOnlyEraser)
	if !ok {
		return nil, nil, errors.New("queue erase requires the Lane B queue-only operation")
	}
	validator, err := idtoken.NewValidator(ctx)
	if err != nil {
		return nil, nil, errors.New("could not initialize workload identity validation")
	}
	markers, err := docstore.Open(ctx, docstore.Config{
		Project: cfg.erase.markerProject, Database: cfg.erase.markerDatabase,
	})
	if err != nil {
		return nil, nil, errors.New("could not open deletion marker reader")
	}
	reader, ok := any(markers).(deletionMarkerReader)
	if !ok {
		closeErr := markers.Close()
		return nil, nil, errors.Join(errors.New("queue erase requires the Lane B deletion marker reader"), closeErr)
	}
	handler := eraseEndpoint{
		authorize: authorizeErase(validator, cfg.erase),
		markers:   reader,
		erase:     eraser.EraseQueue,
		report:    func(err error) { reportQueueError(logger, "erase", err) },
	}
	server := newServer(cfg.erase.port, handler.routes())
	server.WriteTimeout = 9 * time.Second
	return server, func() {
		if closeErr := markers.Close(); closeErr != nil {
			logger.Warn("close deletion marker reader failed")
		}
	}, nil
}
