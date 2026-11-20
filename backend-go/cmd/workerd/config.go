package main

import (
	"errors"
	"fmt"
	"net"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const gateAbandoned queue.Cause = "gate_abandoned"

type config struct {
	policy           queue.Config
	erase            eraseConfig
	databaseURL      string
	firestoreProject string
	encryptionSecret string
	healthPort       int
	metricsPort      int
	stopTimeout      time.Duration
}

type lookupEnv func(string) (string, bool)

var projectID = regexp.MustCompile(`^[a-z][a-z0-9-]{4,28}[a-z0-9]$`)

func readConfig(lookup lookupEnv, migrate bool) (config, error) {
	database, _ := lookup("DATABASE_URL")
	if !validDatabaseURL(database) {
		return config{}, errors.New("DATABASE_URL must be an explicit PostgreSQL URL with host, user and database")
	}
	cfg := config{databaseURL: database}
	if err := cfg.readPolicy(lookup); err != nil {
		return config{}, err
	}
	if err := cfg.policy.Validate(); err != nil {
		return config{}, err
	}
	if migrate {
		return cfg, nil
	}
	if err := cfg.readWorkerConfig(lookup); err != nil {
		return config{}, err
	}
	if err := cfg.readEraseConfig(lookup); err != nil {
		return config{}, err
	}
	return cfg, nil
}

func (c *config) readWorkerConfig(lookup lookupEnv) error {
	c.firestoreProject, _ = lookup("FIRESTORE_PROJECT")
	c.encryptionSecret, _ = lookup("ENCRYPTION_SECRET")
	if !projectID.MatchString(c.firestoreProject) {
		return errors.New("FIRESTORE_PROJECT must be a Google Cloud project ID")
	}
	if err := crypt.Check(c.encryptionSecret); err != nil {
		return fmt.Errorf("ENCRYPTION_SECRET: %w", err)
	}
	if c.healthPort == c.metricsPort {
		return errors.New("HEALTH_PORT and METRICS_PORT must differ")
	}
	return nil
}

func validDatabaseURL(raw string) bool {
	u, err := url.Parse(raw)
	if err != nil || (u.Scheme != "postgres" && u.Scheme != "postgresql") {
		return false
	}
	if u.Hostname() == "" || u.User == nil || u.User.Username() == "" || len(u.Path) < 2 {
		return false
	}
	parsed, err := pgxpool.ParseConfig(raw)
	if err != nil {
		return false
	}
	if configUsesOnlyLoopback(parsed) {
		return true
	}
	if parsed.ConnConfig.TLSConfig == nil {
		return false
	}
	for _, fallback := range parsed.ConnConfig.Fallbacks {
		if fallback.TLSConfig == nil {
			return false
		}
	}
	return true
}

func configUsesOnlyLoopback(parsed *pgxpool.Config) bool {
	if !isLoopbackHost(parsed.ConnConfig.Host) {
		return false
	}
	for _, fallback := range parsed.ConnConfig.Fallbacks {
		if !isLoopbackHost(fallback.Host) {
			return false
		}
	}
	return true
}

func isLoopbackHost(host string) bool {
	if ip := net.ParseIP(host); ip != nil {
		return ip.IsLoopback()
	}
	return strings.EqualFold(strings.TrimSuffix(host, "."), "localhost")
}

func (c *config) readPolicy(lookup lookupEnv) error {
	p := &c.policy
	p.GateAbandoned = gateAbandoned
	settings := []struct {
		name             string
		defaultValue     int
		minimum, maximum int
		set              func(int)
	}{
		{"HEALTH_PORT", 8080, 1, 65535, func(n int) { c.healthPort = n }},
		{"METRICS_PORT", 9090, 1, 65535, func(n int) { c.metricsPort = n }},
		{"SHUTDOWN_SECONDS", 25, 5, 300, func(n int) { c.stopTimeout = time.Duration(n) * time.Second }},
		{"WORKERS", 4, 1, 64, func(n int) { p.Workers = n }},
		{"LEASE_SECONDS", 60, 3, 86400, func(n int) { p.Lease = time.Duration(n) * time.Second }},
		{"BACKOFF_BASE_MS", 1000, 1, 86400000, func(n int) { p.Backoff = time.Duration(n) * time.Millisecond }},
		{"BUDGET_REQUEUE_SECONDS", 2700, 0, 31536000, func(n int) { p.BudgetDelay = time.Duration(n) * time.Second }},
		{"GATE_TIMEOUT_SECONDS", 1209600, 1, 31536000, func(n int) { p.GateTimeout = time.Duration(n) * time.Second }},
		{"MAX_ATTEMPTS", 5, 1, 1000000, func(n int) { p.MaxAttempts = n }},
		{"DETERMINISTIC_MAX_ATTEMPTS", 4, 1, 1000000, func(n int) { p.DeterministicMax = n }},
		{"RECONCILE_MAX_ATTEMPTS", 20, 1, 1000000, func(n int) { p.ReconcileMax = n }},
	}
	for _, setting := range settings {
		value := setting.defaultValue
		if raw, ok := lookup(setting.name); ok {
			parsed, err := strconv.Atoi(raw)
			if err != nil || parsed < setting.minimum || parsed > setting.maximum {
				return fmt.Errorf("%s must be an integer between %d and %d", setting.name, setting.minimum, setting.maximum)
			}
			value = parsed
		}
		setting.set(value)
	}
	return nil
}
