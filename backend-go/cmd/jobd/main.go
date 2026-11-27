package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/conformance/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/conformance/kitstore"
	wire "github.com/BasedHardware/omi/backend-go/internal/conformance/stubapi"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/queue"

	"github.com/jackc/pgx/v5/pgconn"
)

func main() {
	if err := command(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func command(args []string) error {
	if len(args) == 0 {
		return errArgument
	}
	if args[0] == "crypt" {
		err := cryptCLI(crypt.New(os.Getenv("ENCRYPTION_SECRET")), args[1:], os.Stdin, os.Stdout)
		switch {
		case err == nil, errors.Is(err, errArgument), errors.Is(err, crypt.ErrUnreadable):
			return err
		default:
			return errors.New("temporarily_unavailable")
		}
	}
	if len(args) != 1 || args[0] != "migrate" && args[0] != "serve" {
		return errArgument
	}
	cfg, err := loadConfig()
	if err != nil {
		return err
	}
	if cfg.database == "" {
		return errors.New("DATABASE_URL required")
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	dbCtx, end := context.WithTimeout(ctx, 20*time.Second)
	defer end()
	m := &metrics{counters: make(map[string]uint64), histograms: make(map[string]histogram)}
	store, err := queue.Open(dbCtx, cfg.database, cfg.Config, kinds(), m, clock.System{})
	if errors.Is(err, queue.ErrConfig) {
		return errors.New("invalid queue configuration")
	}
	if err != nil {
		return errors.New("database connection failed")
	}
	defer store.Close()
	m.declare(store.Causes())
	kit, err := kitstore.Open(dbCtx, cfg.database)
	if err != nil {
		return errors.New("database connection failed")
	}
	defer kit.Close()
	if args[0] == "migrate" {
		if err := errors.Join(store.Migrate(dbCtx), kit.Migrate(dbCtx)); err != nil {
			return errors.New("database migration failed")
		}
		return nil
	}
	if cfg.secret == "" {
		return errors.New("ENCRYPTION_SECRET required")
	}
	if err := crypt.Check(cfg.secret); err != nil {
		return err
	}
	if store.Ready(dbCtx) != nil {
		return errors.New("database migrations required")
	}
	return serve(ctx, cfg, store, kit, m)
}

func serve(ctx context.Context, cfg config, store *queue.Store, kit *kitstore.Store, m *metrics) error {
	client, err := wire.New(cfg.stub, cfg.Workers, m, clock.System{})
	if err != nil {
		return err
	}
	defer client.Close()

	var listener net.ListenConfig
	address := ":" + cfg.port
	if cfg.replayListen {
		address = "127.0.0.1:0"
	}
	ln, err := listener.Listen(ctx, "tcp", address)
	if err != nil {
		return errors.New("listen failed")
	}
	final := &finalization.Service{Store: store, Wire: client, Codec: crypt.New(cfg.secret),
		Warn: func(hash string, cause queue.Cause) {
			slog.Warn("best effort step failed", "job", hash, "cause", cause)
		}}
	units := &batchunit.Service{
		Queue: store, Speech: wire.BatchSpeech{Client: client, Inputs: kit}, Results: wire.BatchResults{Store: kit},
		Accounts: wire.BatchAccounts{Client: client}, Observer: wire.BatchObserver{Client: client}, Keys: wire.BatchKey,
	}
	workers, err := queue.Start(ctx, store, map[string]queue.Handler{
		finalization.Kind: final, batchunit.Kind: units,
	}, reportQueueError)
	if err != nil {
		return errors.New("invalid worker registration")
	}
	defer workers.Stop()
	stopChecks := startEntitlementChecks(ctx, store, units.Entitlement)
	defer stopChecks()

	api := &api{store: store, workers: workers, client: client, final: final, units: units, kit: kit, metrics: m}
	server := &http.Server{Handler: api.routes(), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second,
		WriteTimeout: 90 * time.Second, IdleTimeout: 75 * time.Second, MaxHeaderBytes: 32 << 10,
		BaseContext: func(net.Listener) context.Context { return ctx },
	}
	if cfg.replayListen {
		if _, err := fmt.Fprintln(os.Stdout, ln.Addr().String()); err != nil {
			return errors.Join(errors.New("publish replay listener"), ln.Close())
		}
	}
	stopped := make(chan error, 1)
	go func() { stopped <- server.Serve(ln) }()
	select {
	case err := <-stopped:
		if !errors.Is(err, http.ErrServerClosed) {
			return errors.New("HTTP server failed")
		}
	case <-ctx.Done():
		// The root context is already cancelled; shutdown gets its own deadline.
		shutdown, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer cancel()
		if server.Shutdown(shutdown) != nil {
			if err := server.Close(); err != nil {
				slog.Warn("forced server close failed")
			}
		}
		if err := <-stopped; !errors.Is(err, http.ErrServerClosed) {
			return errors.New("HTTP server failed")
		}
	}
	return nil
}

func reportQueueError(err error) {
	if pg, ok := errors.AsType[*pgconn.PgError](err); ok {
		slog.Warn("queue operation failed", "cause", wire.CauseTransport, "sqlstate", pg.Code)
		return
	}
	slog.Warn("queue operation failed", "cause", wire.CauseTransport)
}

func startEntitlementChecks(ctx context.Context, store *queue.Store, read queue.EntitlementReader) func() {
	ctx, cancel := context.WithCancel(ctx)
	done := make(chan struct{})
	go func() {
		defer close(done)
		tick := time.NewTicker(time.Minute)
		defer tick.Stop()
		for {
			if err := store.CheckEntitlements(ctx, read); err != nil && ctx.Err() == nil {
				reportQueueError(err)
			}
			select {
			case <-ctx.Done():
				return
			case <-tick.C:
			}
		}
	}()
	return func() { cancel(); <-done }
}
