package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/conformance/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/conformance/kitstore"
	wire "github.com/BasedHardware/omi/backend-go/internal/conformance/stubapi"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type api struct {
	store   *queue.Store
	workers *queue.Workers
	client  *wire.Client
	final   *finalization.Service
	units   *batchunit.Service
	kit     *kitstore.Store
	metrics *metrics
}

func (a *api) routes() http.Handler {
	m := http.NewServeMux()
	m.HandleFunc("GET /healthz", a.health)
	m.HandleFunc("POST /v1/conversations/{cid}/end", a.admit)
	m.HandleFunc("POST /v1/batch/{owner}/units", a.batch)
	m.HandleFunc("POST /v1/batch/{owner}/entitlement-changed", a.entitlementChanged)
	m.HandleFunc("GET /v1/jobs/{id}", a.get)
	m.HandleFunc("POST /v1/jobs/{id}/resume", a.resume)
	m.HandleFunc("GET /v1/admin/parked", a.parked)
	m.HandleFunc("POST /v1/admin/jobs/{id}/redrive", a.redrive)
	m.HandleFunc("POST /v1/users/{uid}/erase", a.erase)
	m.HandleFunc("GET /metrics", a.prometheus)
	// The standard mux cleans literal dot path segments. An identifier is
	// an opaque segment, whether the caller escaped those dots or not.
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw := r.URL.EscapedPath()
		if strings.Contains(raw, "/./") || strings.Contains(raw, "/../") ||
			strings.HasSuffix(raw, "/.") || strings.HasSuffix(raw, "/..") {
			parts := strings.Split(raw, "/")
			for i, part := range parts {
				if part == "." || part == ".." {
					parts[i] = strings.ReplaceAll(part, ".", "%2E")
				}
			}
			u := *r.URL
			u.RawPath = strings.Join(parts, "/")
			clone := r.WithContext(r.Context())
			clone.URL = &u
			r = clone
		}
		m.ServeHTTP(w, r)
	})
}

type empty struct{}
type jobID struct {
	ID string `json:"job_id"`
}
type errorBody struct {
	Error string `json:"error"`
}

func respond(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		// The status line is already sent; the client sees a truncated body.
		slog.Warn("response write failed", "status", status)
	}
}

func refusal(w http.ResponseWriter, status int, code string) { respond(w, status, errorBody{code}) }
func unavailable(w http.ResponseWriter)                      { refusal(w, 503, "temporarily_unavailable") }

func routeError(w http.ResponseWriter, err error, conflict string) {
	var refused finalization.Refusal
	var f *wire.Fault
	switch {
	case errors.Is(err, queue.ErrErased):
		refusal(w, 410, "user_erased")
	case errors.Is(err, queue.ErrAbsent):
		refusal(w, 404, "not_found")
	case errors.Is(err, queue.ErrHoldMetadata):
		refusal(w, http.StatusUnprocessableEntity, "held_unit_requires_custody_deadline_and_positive_duration")
	case errors.Is(err, batchunit.ErrInvalid):
		refusal(w, http.StatusBadRequest, "invalid_batch_unit")
	case errors.Is(err, queue.ErrState):
		refusal(w, 409, conflict)
	case errors.As(err, &f) && f.Cause == wire.CauseAccountDeleting:
		refusal(w, 409, "account_deleting")
	case errors.Is(err, queue.ErrDeferred):
		// The tenant is busy (another claim, a guard or an erase holds it). Try again.
		refusal(w, 409, "tenant_busy")
	case errors.As(err, &refused):
		status := 409
		switch refused {
		case finalization.Missing:
			status = 404
		case finalization.Tombstoned:
			status = 410
		case finalization.AlreadyCompleted, finalization.AlreadyFailed, finalization.Discarded,
			finalization.RevisionConflict, finalization.Deleting:
		}
		refusal(w, status, string(refused))
	default:
		unavailable(w)
	}
}

func decode(w http.ResponseWriter, r *http.Request, value any) bool {
	d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4<<20))
	if d.Decode(value) == nil && d.Decode(new(json.RawMessage)) == io.EOF {
		return true
	}
	refusal(w, 400, "invalid_request")
	return false
}

func validID(s string) bool {
	return s != "" && len(s) <= 2048 && utf8.ValidString(s) && !strings.ContainsRune(s, 0)
}

func (a *api) health(w http.ResponseWriter, r *http.Request) {
	if a.store.Ping(r.Context()) != nil {
		unavailable(w)
		return
	}
	respond(w, 200, empty{})
}

func (a *api) admit(w http.ResponseWriter, r *http.Request) {
	var data finalization.Admission
	if !decode(w, r, &data) {
		return
	}
	cid := r.PathValue("cid")
	if !data.Valid() || !validID(data.UID) || !validID(cid) {
		refusal(w, 400, "invalid_request")
		return
	}
	id, err := a.final.Admit(r.Context(), cid, data)
	if err != nil {
		routeError(w, err, "revision_conflict")
		return
	}
	respond(w, 202, jobID{id})
}

// entitlementChanged accepts an owner notification. Only the account source supplies authority.
func (a *api) entitlementChanged(w http.ResponseWriter, r *http.Request) {
	owner := r.PathValue("owner")
	if !validID(owner) {
		refusal(w, 400, "invalid_request")
		return
	}
	ctx := r.Context()
	err := a.store.Tenant(ctx, owner, func(sc *queue.Scope) error {
		fact, err := a.units.Entitlement(ctx, sc.Admitting(), owner)
		if err != nil {
			return err
		}
		return sc.ObserveEntitlement(ctx, fact)
	})
	if err != nil {
		routeError(w, err, "")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// unitWire is the kit's JSON shape for a batch unit. The kit sends the input inline; the
// kind takes a reference, so the input is put in the kit store first and the unit points at it.
type unitWire struct {
	CustodyDeadline time.Time       `json:"custody_deadline"`
	DurationSeconds float64         `json:"duration_seconds"`
	Route           batchunit.Route `json:"route"`
	ID              string          `json:"unit_id"`
	Input           *string         `json:"input"`
	OrderAt         time.Time       `json:"order_at"`
	RunAt           time.Time       `json:"run_at"`
}

func (a *api) batch(w http.ResponseWriter, r *http.Request) {
	var data unitWire
	if !decode(w, r, &data) {
		return
	}
	owner := r.PathValue("owner")
	if data.Input == nil || data.OrderAt.IsZero() || !validID(owner) || !validID(data.ID) {
		refusal(w, 400, "invalid_request")
		return
	}
	ref := wire.BatchKey(owner, data.ID)
	ctx := r.Context()
	var alreadyPaid bool
	err := a.store.Tenant(ctx, owner, func(sc *queue.Scope) error {
		var err error
		alreadyPaid, err = a.kit.StageInput(ctx, sc.Admitting(), ref, *data.Input, queue.OperationID(ref, batchunit.StepSpeech))
		return err
	})
	if err != nil {
		routeError(w, err, "")
		return
	}
	unit := batchunit.Unit{
		ID: data.ID, Source: batchunit.Source{Ref: ref, Version: 1}, OrderAt: data.OrderAt, RunAt: data.RunAt,
		AlreadyPaid: alreadyPaid, Route: data.Route, CustodyDeadline: data.CustodyDeadline,
		AudioDuration: time.Duration(data.DurationSeconds * float64(time.Second)),
	}
	j, err := a.units.Admit(ctx, owner, unit)
	if err != nil {
		routeError(w, err, "")
		return
	}
	respond(w, 202, jobID{j.Key})
}

// jobWire is the kit's JSON shape for a job. The queue's own types carry no wire tags: the
// mapping from domain to wire lives here, at the edge.
type jobWire struct {
	Key                   string          `json:"job_id"`
	Kind                  string          `json:"kind"`
	State                 string          `json:"state"`
	Step                  string          `json:"step"`
	Attempts              int             `json:"attempts"`
	DeterministicAttempts int             `json:"deterministic_attempts"`
	BudgetRequeues        int             `json:"budget_requeues"`
	Token                 int64           `json:"lease_token"`
	Reason                *queue.Cause    `json:"reason"`
	Outcome               *queue.Terminal `json:"outcome"`
	CreatedAt             time.Time       `json:"created_at"`
	UpdatedAt             time.Time       `json:"updated_at"`
}

func wireState(s queue.State) string {
	// The kit names the gated wait after the feature that uses it.
	if s == queue.StateBlocked {
		return "blocked_byok"
	}
	return string(s)
}

func toWire(j queue.Job) jobWire {
	return jobWire{
		Key: j.Key, Kind: j.Kind, State: wireState(j.State), Step: j.Step, Attempts: j.Attempts,
		DeterministicAttempts: j.DeterministicAttempts, BudgetRequeues: j.BudgetRequeues, Token: j.Token,
		Reason: j.Reason, Outcome: j.Outcome, CreatedAt: j.CreatedAt, UpdatedAt: j.UpdatedAt,
	}
}

// jobView is the kit's view of a job. For a batch unit it carries the transcription, read
// from the kit store: the job row itself holds only the receipt.
func (a *api) jobView(ctx context.Context, j queue.Job) (any, error) {
	if j.Kind == finalization.Kind {
		return struct {
			jobWire
			finalization.Metadata
		}{toWire(j), finalization.Meta(j)}, nil
	}
	view := struct {
		jobWire
		Result *string `json:"result"`
	}{jobWire: toWire(j)}
	if receipt, ok := batchunit.Stored(j.Checkpoint); ok {
		text, err := a.kit.Result(ctx, receipt.Result)
		if err != nil && !errors.Is(err, kitstore.ErrAbsent) {
			return nil, err
		}
		if err == nil {
			view.Result = &text
		}
	}
	return view, nil
}

func (a *api) get(w http.ResponseWriter, r *http.Request) {
	j, err := a.store.Get(r.Context(), r.PathValue("id"))
	if err != nil {
		routeError(w, err, "")
		return
	}
	view, err := a.jobView(r.Context(), j)
	if err != nil {
		unavailable(w)
		return
	}
	respond(w, 200, view)
}

func (a *api) resume(w http.ResponseWriter, r *http.Request) {
	id, key := r.PathValue("id"), r.Header.Get("X-Omi-Vendor-Key")
	if key == "" || key == "platform" || len(key) > 8192 {
		refusal(w, 400, "invalid_request")
		return
	}
	if err := a.workers.Resume(r.Context(), id, key); err != nil {
		routeError(w, err, "not_blocked")
		return
	}
	respond(w, 202, jobID{id})
}

func (a *api) parked(w http.ResponseWriter, r *http.Request) {
	jobs, err := a.store.Parked(r.Context(), r.URL.Query().Get("uid"))
	if err != nil {
		routeError(w, err, "")
		return
	}
	result := make([]any, 0, len(jobs))
	for _, j := range jobs {
		view, err := a.jobView(r.Context(), j)
		if err != nil {
			unavailable(w)
			return
		}
		result = append(result, view)
	}
	respond(w, 200, result)
}

func (a *api) redrive(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if err := a.store.Redrive(r.Context(), id); err != nil {
		routeError(w, err, "not_parked")
		return
	}
	respond(w, 202, jobID{id})
}

func (a *api) erase(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	uid := r.PathValue("uid")
	if !validID(uid) {
		refusal(w, 400, "invalid_request")
		return
	}
	err := a.store.Erase(ctx, uid, func() error {
		if err := a.kit.Erase(ctx, uid); err != nil {
			return err
		}
		if fault := a.client.Erase(ctx, uid); fault != nil {
			return fault
		}
		return nil
	})
	if err != nil {
		unavailable(w)
		return
	}
	respond(w, 200, empty{})
}
