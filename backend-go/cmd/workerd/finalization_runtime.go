package main

import (
	"context"
	"errors"
	"log/slog"
	"time"

	"google.golang.org/api/idtoken"
	"google.golang.org/api/option"
	gcs "google.golang.org/api/storage/v1"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/finalizationdocs"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func workerdKinds() []queue.Kind {
	causes := append(finalizationdocs.Causes(), conversations.Causes()...)
	return []queue.Kind{finalization.Declaration(causes...)}
}

func workerdHandlers(family *finalization.Service) map[string]queue.Handler {
	// The declaration is safe to register independently of the consumer.
	// A binary with missing serving ports must leave queued intents untouched.
	if family == nil || family.Queue == nil || family.Outbox == nil || family.Lifecycle == nil ||
		family.Documents == nil || family.Replay == nil || family.Gateway == nil ||
		family.Meeting == nil || family.Batch == nil || family.Effects == nil ||
		family.Targets == nil || family.Integrations == nil {
		return nil
	}
	return map[string]queue.Handler{finalization.Kind: family}
}

type finalizationRuntime struct {
	family  *finalization.Service
	docs    *docstore.Store
	scan    *finalizationdocs.SummaryScan
	retract *httpx.Client
}

func openFinalizationRuntime(ctx, startup context.Context, cfg config, q *queue.Store) (finalizationRuntime, error) {
	if !cfg.summaryRepair && cfg.privateArchive == "" && cfg.retractionOrigin == "" {
		return finalizationRuntime{}, nil
	}
	docs, err := docstore.Open(startup, docstore.Config{Project: cfg.firestoreProject})
	if err != nil {
		return finalizationRuntime{}, errors.New("could not open finalization document store")
	}
	clk := clock.System{}
	store := finalizationdocs.Store{Docs: docs, Clock: clk, Codec: crypt.New(cfg.encryptionSecret)}
	runtime := finalizationRuntime{docs: docs, family: &finalization.Service{Queue: q}}
	if bindErr := runtime.bindMaintenanceAdapters(ctx, startup, cfg, &store); bindErr != nil {
		return finalizationRuntime{}, errors.Join(bindErr, runtime.close())
	}
	wireFinalizationDocuments(runtime.family, store)
	if cfg.summaryRepair {
		runtime.scan = &finalizationdocs.SummaryScan{Docs: docs, Family: runtime.family, Clock: clk, MaxAge: cfg.summaryMaxAge}
	}
	return runtime, nil
}

func (m *finalizationRuntime) bindMaintenanceAdapters(ctx, startup context.Context, cfg config, store *finalizationdocs.Store) error {
	if cfg.privateArchive != "" {
		client, err := gcs.NewService(startup, option.WithScopes(gcs.DevstorageReadOnlyScope))
		if err != nil {
			return errors.New("could not open recording archive inventory")
		}
		store.Archive = finalizationdocs.GCSArchive{Objects: client.Objects, Private: cfg.privateArchive, Derived: cfg.derivedArchive}
	}
	if cfg.retractionOrigin == "" {
		return nil
	}
	tokens, err := idtoken.NewTokenSource(ctx, cfg.retractionAudience)
	if err != nil {
		return errors.New("could not configure merge retraction identity")
	}
	client, err := httpx.New(cfg.retractionOrigin, cfg.policy.Workers, 75*time.Second, store.Clock)
	if err != nil {
		return errors.New("could not open merge retraction transport")
	}
	store.MergeRetraction = finalizationdocs.HTTPMergeRetraction{Client: client, Bearer: func(ctx context.Context) (string, error) {
		if err := ctx.Err(); err != nil {
			return "", err
		}
		token, err := tokens.Token()
		if err != nil {
			return "", err
		}
		return token.AccessToken, nil
	}}
	m.retract = client
	return nil
}

func (m *finalizationRuntime) close() error {
	if m.retract != nil {
		m.retract.Close()
	}
	if m.docs != nil {
		if err := m.docs.Close(); err != nil {
			return errors.New("could not close finalization document store")
		}
	}
	return nil
}

func (m *finalizationRuntime) run(ctx context.Context, logger *slog.Logger) {
	if m.scan == nil {
		return
	}
	const interval = 2 * time.Minute
	tick := time.NewTicker(interval)
	defer tick.Stop()
	for ctx.Err() == nil {
		counts, err := m.scan.Tick(ctx)
		if ctx.Err() == nil && (err != nil || counts.Errors != 0) {
			logger.Warn("summary debt repair needs retry", "failed_admissions", counts.Errors)
		}
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
		}
	}
}
