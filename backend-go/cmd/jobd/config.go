package main

import (
	"errors"
	"os"
	"strconv"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/conformance/finalization"
	wire "github.com/BasedHardware/omi/backend-go/internal/conformance/stubapi"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type config struct {
	queue.Config
	port         string
	replayListen bool
	database     string
	stub         string
	secret       string
}

func loadConfig() (config, error) {
	c := config{
		database:     os.Getenv("DATABASE_URL"),
		replayListen: os.Getenv("JOBD_REPLAY_LISTEN") == "1",
		stub:         os.Getenv("STUB_URL"), secret: os.Getenv("ENCRYPTION_SECRET"),
	}
	values := []struct {
		name              string
		fallback, ceiling int
		set               func(int)
	}{
		{"PORT", 8080, 65535, func(n int) { c.port = strconv.Itoa(n) }},
		{"WORKERS", 8, 64, func(n int) { c.Workers = n }},
		{"LEASE_SECONDS", 60, 86400, func(n int) { c.Lease = time.Duration(n) * time.Second }},
		{"MAX_ATTEMPTS", 5, 1000000, func(n int) { c.MaxAttempts = n }},
		{"DETERMINISTIC_MAX_ATTEMPTS", 4, 1000000, func(n int) { c.DeterministicMax = n }},
		{"BUDGET_REQUEUE_SECONDS", 2700, 31536000, func(n int) { c.BudgetDelay = time.Duration(n) * time.Second }},
		{"BYOK_ABANDON_SECONDS", 1209600, 31536000, func(n int) { c.GateTimeout = time.Duration(n) * time.Second }},
		{"BACKOFF_BASE_MS", 1000, 86400000, func(n int) { c.Backoff = time.Duration(n) * time.Millisecond }},
	}
	for _, v := range values {
		n := v.fallback
		if raw, ok := os.LookupEnv(v.name); ok {
			var err error
			n, err = strconv.Atoi(raw)
			floor := 1
			if v.name == "BUDGET_REQUEUE_SECONDS" || v.name == "BYOK_ABANDON_SECONDS" {
				floor = 0
			}
			if err != nil || n < floor || n > v.ceiling {
				return config{}, errors.New("invalid " + v.name)
			}
		}
		v.set(n)
	}
	c.GateAbandoned = finalization.CauseBYOKAbandoned
	// The kit has no setting for this. Twenty tries with capped backoff outlast every
	// outage the kit injects and still end.
	c.ReconcileMax = reconcileMax
	return c, nil
}

const reconcileMax = 20

// kinds declares every kind this binary admits or runs, each with the causes of the
// adapters it is wired to. This is the one place a new kind is added.
func kinds() []queue.Kind {
	return []queue.Kind{finalization.Declaration(wire.Causes()...), batchunit.Declaration(wire.Causes()...)}
}
