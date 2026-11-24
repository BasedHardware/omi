package main

import (
	"context"
	"errors"
	"net/url"
	"strings"
	"time"

	"google.golang.org/api/idtoken"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/syncfinalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
)

func (c *config) readFinalizationReference(lookup lookupEnv) error {
	origin, _ := lookup("WORKER_SYNC_FINALIZATION_REFERENCE_ORIGIN")
	audience, _ := lookup("WORKER_SYNC_FINALIZATION_REFERENCE_AUDIENCE")
	if origin == "" && audience == "" {
		return nil
	}
	u, err := url.Parse(origin)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.RawQuery != "" ||
		u.ForceQuery || u.Fragment != "" || (u.Path != "/" && u.Path != "") || strings.TrimSpace(audience) == "" {
		return errors.New("sync finalization reference requires an HTTPS origin and OIDC audience")
	}
	if c.gateway.BaseURL == "" {
		return errors.New("sync finalization reference requires the keyed finalization gateway")
	}
	if c.quietRecovery || c.summaryRepair {
		return errors.New("ordinary sync finalization must run separately from quiet and summary repair")
	}
	c.referenceOrigin, c.referenceAudience = origin, audience
	return nil
}

func (m *finalizationRuntime) bindFinalizationReference(ctx context.Context, cfg config, clk clock.Clock) error {
	if cfg.referenceOrigin == "" {
		return nil
	}
	tokens, err := idtoken.NewTokenSource(ctx, cfg.referenceAudience)
	if err != nil {
		return errors.New("could not configure sync finalization reference identity")
	}
	client, err := httpx.New(cfg.referenceOrigin, cfg.policy.Workers, 70*time.Second, clk)
	if err != nil {
		return err
	}
	m.reference = client
	reference := syncfinalization.Reference{
		Client: client,
		Bearer: func(ctx context.Context) (string, error) {
			if err := ctx.Err(); err != nil {
				return "", err
			}
			token, err := tokens.Token()
			if err != nil {
				return "", err
			}
			return token.AccessToken, nil
		},
	}
	wireSyncFinalizationReference(m.family, reference)
	return nil
}

func wireSyncFinalizationReference(s *finalization.Service, reference syncfinalization.Reference) {
	s.Meeting = reference
	s.NotesPrompt = reference
	s.Batch = syncfinalization.OrdinaryCustody{}
	s.Effects = reference
	s.Targets = reference
	s.Episodes = reference
}
