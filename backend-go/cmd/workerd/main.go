// Command workerd runs Omi queue workers and exposes private operational endpoints.
package main

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const startupTimeout = 30 * time.Second

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stderr, nil))
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	err := run(ctx, os.Args[1:], logger)
	cancel()
	if err != nil {
		logger.Error("workerd stopped", "reason", err.Error())
		os.Exit(1)
	}
}

func run(ctx context.Context, args []string, logger *slog.Logger) error {
	migrate := len(args) == 1 && args[0] == "migrate"
	if len(args) != 0 && !migrate {
		return errors.New("usage: workerd [migrate]")
	}
	cfg, err := readConfig(os.LookupEnv, migrate)
	if err != nil {
		return err
	}

	kinds := workerdKinds()
	registry := prometheus.NewRegistry()
	metrics := newQueueMetrics(registry, kinds, cfg.policy.GateAbandoned)

	startup, endStartup := context.WithTimeout(ctx, startupTimeout)
	store, err := queue.Open(startup, cfg.databaseURL, cfg.policy, kinds, metrics, clock.System{})
	if err != nil {
		reportQueueError(logger, "open", err)
		endStartup()
		return errors.New("could not open PostgreSQL queue")
	}
	if migrate {
		defer store.Close()
		defer endStartup()
		if migrationErr := store.Migrate(startup); migrationErr != nil {
			reportQueueError(logger, "migrate", migrationErr)
			return errors.New("could not migrate PostgreSQL queue")
		}
		return nil
	}
	if readyErr := store.Ready(startup); readyErr != nil {
		reportQueueError(logger, "ready", readyErr)
		endStartup()
		store.Close()
		return errors.New("could not verify PostgreSQL queue schema; check connectivity and migration state")
	}
	maintenance, err := openFinalizationRuntime(ctx, startup, cfg, store)
	if err != nil {
		endStartup()
		store.Close()
		return err
	}
	defer func() {
		if closeErr := maintenance.close(); closeErr != nil {
			logger.Warn("could not close finalization adapters")
		}
	}()
	handlers := workerdHandlers(maintenance.family)

	eraseServer, closeErase, err := openEraseServer(startup, cfg, store, logger)
	endStartup()
	if err != nil {
		store.Close()
		return err
	}
	defer closeErase()

	workers, err := queue.Start(ctx, store, handlers, func(err error) {
		reportQueueError(logger, "worker", err)
	})
	if err != nil {
		reportQueueError(logger, "start_workers", err)
		store.Close()
		return errors.New("could not start queue workers")
	}
	registry.MustRegister(newStrandedCollector(workers), newCustomerWaitCollector(store))

	return serve(ctx, cfg, store, workers, registry, func(ctx context.Context) {
		maintenance.run(ctx, logger)
	}, maintenance.privateFinalizationHandlers(cfg), eraseServer)
}
