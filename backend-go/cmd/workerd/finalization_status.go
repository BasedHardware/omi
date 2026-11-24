package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"

	"google.golang.org/api/idtoken"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
)

const finalizationStatusPath = "/internal/finalization/status"
const finalizationStatusReaders = 4

type finalizationStatusEndpoint struct {
	audience, caller string
	validate         func(context.Context, string, string) (*idtoken.Payload, error)
	lookup           func(context.Context, finalization.Ref, int64) (finalization.JobStatus, error)
	slots            chan struct{}
}

func (m *finalizationRuntime) privateFinalizationHandlers(cfg config) http.Handler {
	intake := m.episodeIntakeHandler(cfg)
	if intake == nil {
		return nil
	}
	mux := http.NewServeMux()
	mux.Handle("POST "+episodeIntakePath, intake)
	mux.Handle("POST "+finalizationStatusPath, finalizationStatusEndpoint{
		audience: cfg.episodeIntakeAudience, caller: cfg.episodeIntakeCaller,
		validate: idtoken.Validate, lookup: m.family.Status,
		slots: make(chan struct{}, finalizationStatusReaders),
	})
	return mux
}

func (h finalizationStatusEndpoint) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), probeTimeout)
	defer cancel()
	if !authorizedWorkerCaller(ctx, r.Header.Get("Authorization"), h.audience, h.caller, h.validate) {
		w.WriteHeader(http.StatusForbidden)
		return
	}
	var req struct {
		Owner        string `json:"owner"`
		Conversation string `json:"conversation"`
		Job          string `json:"job"`
		Revision     int64  `json:"revision"`
	}
	d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 2048))
	d.DisallowUnknownFields()
	ref := finalization.Ref{}
	if err := d.Decode(&req); err == nil {
		ref = finalization.Ref{Owner: req.Owner, ID: req.Conversation}
	}
	if !validIntakeID(ref.Owner) || !validIntakeID(ref.ID) || req.Revision <= 0 ||
		req.Job != finalization.JobID(ref, req.Revision) || !errors.Is(d.Decode(new(any)), io.EOF) {
		w.WriteHeader(http.StatusBadRequest)
		return
	}
	h.read(ctx, w, ref, req.Revision)
}

func (h finalizationStatusEndpoint) read(ctx context.Context, w http.ResponseWriter, ref finalization.Ref, revision int64) {
	select {
	case h.slots <- struct{}{}:
		defer func() { <-h.slots }()
	default:
		w.WriteHeader(http.StatusServiceUnavailable)
		return
	}
	result, err := h.lookup(ctx, ref, revision)
	switch {
	case errors.Is(err, finalization.ErrStale):
		w.WriteHeader(http.StatusNotFound)
	case err != nil:
		w.WriteHeader(http.StatusServiceUnavailable)
	default:
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(result); err != nil {
			slog.Debug("could not send workerd finalization status")
		}
	}
}
