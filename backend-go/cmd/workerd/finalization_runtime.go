package main

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"time"

	"google.golang.org/api/cloudkms/v1"
	"google.golang.org/api/idtoken"
	"google.golang.org/api/option"
	gcs "google.golang.org/api/storage/v1"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/finalizationdocs"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/integrations"
	"github.com/BasedHardware/omi/backend-go/internal/adapters/llmgateway"
	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/integrationfanout"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/platform/objectlake"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func workerdKinds() []queue.Kind {
	causes := append(finalizationdocs.Causes(), conversations.Causes()...)
	causes = append(causes, integrationfanout.Causes()...)
	causes = append(causes, llmgateway.Causes()...)
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
	family    *finalization.Service
	docs      *docstore.Store
	scan      *finalizationdocs.SummaryScan
	quiet     *finalizationdocs.QuietScan
	retract   *httpx.Client
	reference *httpx.Client
	sender    *integrations.Sender
	gateway   llmgateway.Replayable
}

func openFinalizationRuntime(ctx, startup context.Context, cfg config, q *queue.Store) (finalizationRuntime, error) {
	if !cfg.quietRecovery && !cfg.summaryRepair && cfg.privateArchive == "" && cfg.retractionOrigin == "" && cfg.objectBucket == "" &&
		cfg.episodeIntakeAudience == "" && cfg.gateway.BaseURL == "" {
		return finalizationRuntime{}, nil
	}
	docs, err := docstore.Open(startup, docstore.Config{Project: cfg.firestoreProject})
	if err != nil {
		return finalizationRuntime{}, errors.New("could not open finalization document store")
	}
	clk := clock.System{}
	store := finalizationdocs.Store{
		Docs: docs, Clock: clk, Codec: crypt.New(cfg.encryptionSecret), SyncOnly: cfg.referenceOrigin != "",
	}
	runtime := finalizationRuntime{docs: docs, family: &finalization.Service{Queue: q}}
	if bindErr := runtime.bindMaintenanceAdapters(ctx, startup, cfg, &store); bindErr != nil {
		return finalizationRuntime{}, errors.Join(bindErr, runtime.close())
	}
	var offload conversations.TranscriptReader
	if cfg.objectBucket != "" {
		reader, lakeErr := openTranscriptReader(startup, cfg, docs)
		if lakeErr != nil {
			return finalizationRuntime{}, errors.Join(lakeErr, runtime.close())
		}
		offload = reader
	}
	wireFinalizationDocuments(runtime.family, store, offload, cfg.notesDedupe)
	if wireErr := runtime.bindIntegrationDelivery(clk); wireErr != nil {
		return finalizationRuntime{}, errors.Join(wireErr, runtime.close())
	}
	if wireErr := runtime.bindFinalizationGateway(cfg.gateway, clk); wireErr != nil {
		return finalizationRuntime{}, errors.Join(wireErr, runtime.close())
	}
	if wireErr := runtime.bindFinalizationReference(ctx, cfg, clk); wireErr != nil {
		return finalizationRuntime{}, errors.Join(wireErr, runtime.close())
	}
	if cfg.summaryRepair {
		runtime.scan = &finalizationdocs.SummaryScan{Docs: docs, Family: runtime.family, Clock: clk, MaxAge: cfg.summaryMaxAge}
	}
	if registerErr := runtime.registerQuietRecovery(cfg.quietRecovery, store.Archive != nil, clk); registerErr != nil {
		return finalizationRuntime{}, errors.Join(registerErr, runtime.close())
	}
	return runtime, nil
}

func (m *finalizationRuntime) registerQuietRecovery(enabled, hasArchive bool, clk clock.Clock) error {
	if !enabled {
		return nil
	}
	if !hasArchive || len(workerdHandlers(m.family)) == 0 || m.family.Quiet == nil {
		return errors.New("quiet recovery requires the archive and serving finalization handler")
	}
	m.quiet = &finalizationdocs.QuietScan{Docs: m.docs, Family: m.family, Clock: clk}
	return nil
}

func openTranscriptReader(ctx context.Context, cfg config, docs *docstore.Store) (conversations.TranscriptReader, error) {
	storage, err := gcs.NewService(ctx, option.WithScopes(gcs.DevstorageReadOnlyScope))
	if err != nil {
		return nil, errors.New("could not open object-lake storage reader")
	}
	kms, err := cloudkms.NewService(ctx)
	if err != nil {
		return nil, errors.New("could not open object-lake KMS reader")
	}
	return objectlake.Reader{Enabled: true, Bucket: cfg.objectBucket, KMSKey: cfg.objectKMSKey, Docs: docs, Storage: storage, KMS: kms}, nil
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

func (m *finalizationRuntime) bindIntegrationDelivery(clk clock.Clock) error {
	sender, err := integrations.NewSender(10*time.Second, clk)
	if err != nil {
		return err
	}
	m.sender = sender
	m.family.Integrations = integrationDelivery{service: integrationfanout.Service{
		Sender: sender, Receipts: integrations.Receipts{Store: m.docs},
	}}
	return nil
}

func (m *finalizationRuntime) close() error {
	if m.reference != nil {
		m.reference.Close()
	}
	if m.gateway != nil {
		m.gateway.Close()
	}
	if m.sender != nil {
		m.sender.Close()
	}
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
	var loops sync.WaitGroup
	if m.scan != nil {
		loops.Go(func() {
			runMaintenance(ctx, 2*time.Minute, func() {
				counts, err := m.scan.Tick(ctx)
				if ctx.Err() == nil && (err != nil || counts.Errors != 0) {
					logger.Warn("summary debt repair needs retry", "failed_admissions", counts.Errors)
				}
			})
		})
	}
	if m.quiet != nil {
		loops.Go(func() {
			runMaintenance(ctx, 30*time.Second, func() {
				failed, err := m.quiet.Tick(ctx)
				if ctx.Err() == nil && (err != nil || failed > 0) {
					logger.Warn("quiet recovery needs retry", "failed_wakes", failed)
				}
			})
		})
	}
	loops.Wait()
}

func runMaintenance(ctx context.Context, interval time.Duration, tick func()) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for ctx.Err() == nil {
		tick()
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
