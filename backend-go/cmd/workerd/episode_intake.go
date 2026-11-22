package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"google.golang.org/api/idtoken"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const episodeIntakePath = "/internal/finalization/episode-intake"

type episodeIntakeEndpoint struct {
	audience, caller string
	validate         func(context.Context, string, string) (*idtoken.Payload, error)
	attach           func(context.Context, finalization.Ref, time.Time) (string, error)
}

func (m *finalizationRuntime) episodeIntakeHandler(cfg config) http.Handler {
	if cfg.episodeIntakeAudience == "" || cfg.episodeIntakeCaller == "" {
		return nil
	}
	return episodeIntakeEndpoint{
		audience: cfg.episodeIntakeAudience, caller: cfg.episodeIntakeCaller,
		validate: idtoken.Validate, attach: m.family.RepairEpisodeIntake,
	}
}

func (h episodeIntakeEndpoint) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 4*time.Second)
	defer cancel()
	if !h.authorized(ctx, r.Header.Get("Authorization")) {
		w.WriteHeader(http.StatusForbidden)
		return
	}
	var req struct {
		Owner        string    `json:"owner"`
		Conversation string    `json:"conversation"`
		Written      time.Time `json:"written"`
	}
	d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 2048))
	d.DisallowUnknownFields()
	if err := d.Decode(&req); err != nil || !errors.Is(d.Decode(new(any)), io.EOF) ||
		!validIntakeID(req.Owner) || !validIntakeID(req.Conversation) || req.Written.IsZero() {
		w.WriteHeader(http.StatusBadRequest)
		return
	}
	id, err := h.attach(ctx, finalization.Ref{Owner: req.Owner, ID: req.Conversation}, req.Written)
	switch {
	case errors.Is(err, finalization.ErrStale), errors.Is(err, queue.ErrErased):
		w.WriteHeader(http.StatusConflict)
	case err != nil:
		w.WriteHeader(http.StatusServiceUnavailable)
	case id == "":
		w.WriteHeader(http.StatusNoContent)
	default:
		w.WriteHeader(http.StatusOK)
	}
}

func (h episodeIntakeEndpoint) authorized(ctx context.Context, header string) bool {
	token, ok := strings.CutPrefix(header, "Bearer ")
	if !ok || token == "" {
		return false
	}
	p, err := h.validate(ctx, token, h.audience)
	return err == nil && p != nil &&
		(p.Issuer == "https://accounts.google.com" || p.Issuer == "accounts.google.com") &&
		p.Claims["email"] == h.caller && p.Claims["email_verified"] == true
}

func validIntakeID(id string) bool {
	return id != "" && len(id) <= 256 && id != "." && id != ".." && !strings.ContainsRune(id, '/')
}
