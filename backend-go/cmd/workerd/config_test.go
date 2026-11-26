package main

import (
	"strings"
	"testing"
	"time"
)

func fixtureEnv() map[string]string {
	return map[string]string{
		"DATABASE_URL":      "postgres://workerd:synthetic@localhost/queue?sslmode=require",
		"FIRESTORE_PROJECT": "demo-workerd",
		"ENCRYPTION_SECRET": strings.Repeat("t", 32),
	}
}

func envLookup(env map[string]string) lookupEnv {
	return func(key string) (string, bool) {
		value, ok := env[key]
		return value, ok
	}
}

func TestConfigRefusesInvalidSettingsWithoutEchoingInputs(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct{ name, key, input string }{
		{"empty database URL", "DATABASE_URL", ""},
		{"database URL scheme", "DATABASE_URL", "https://sensitive@localhost/queue"},
		{"database URL host", "DATABASE_URL", "postgres://synthetic@/queue"},
		{"database URL user", "DATABASE_URL", "postgres://localhost/queue"},
		{"database URL name", "DATABASE_URL", "postgres://synthetic@localhost"},
		{"database URL invalid options", "DATABASE_URL", "postgres://synthetic@localhost/queue?sslmode=invalid"},
		{"remote database URL disables TLS", "DATABASE_URL", "postgres://workerd:synthetic@db.example.test/queue?sslmode=disable"},
		{"remote database URL allows TLS downgrade", "DATABASE_URL", "postgres://workerd:synthetic@db.example.test/queue?sslmode=prefer"},
		{"remote database URL defaults to TLS downgrade", "DATABASE_URL", "postgres://workerd:synthetic@db.example.test/queue"},
		{"empty Firestore project", "FIRESTORE_PROJECT", ""},
		{"malformed Firestore project", "FIRESTORE_PROJECT", "projects/demo-workerd"},
		{"empty encryption secret", "ENCRYPTION_SECRET", ""},
		{"short encryption secret", "ENCRYPTION_SECRET", "short-sensitive-secret"},
		{"zero health port", "HEALTH_PORT", "0"},
		{"invalid metrics port", "METRICS_PORT", "65536"},
		{"duplicate listener port", "METRICS_PORT", "8080"},
		{"zero workers", "WORKERS", "0"},
		{"too many workers", "WORKERS", "65"},
		{"malformed worker count", "WORKERS", "invalid"},
		{"lease too short", "LEASE_SECONDS", "2"},
		{"zero backoff", "BACKOFF_BASE_MS", "0"},
		{"negative budget delay", "BUDGET_REQUEUE_SECONDS", "-1"},
		{"zero gate timeout", "GATE_TIMEOUT_SECONDS", "0"},
		{"zero max attempts", "MAX_ATTEMPTS", "0"},
		{"zero deterministic attempts", "DETERMINISTIC_MAX_ATTEMPTS", "0"},
		{"zero reconcile attempts", "RECONCILE_MAX_ATTEMPTS", "0"},
		{"shutdown too short", "SHUTDOWN_SECONDS", "4"},
		{"shutdown too long", "SHUTDOWN_SECONDS", "301"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			env := fixtureEnv()
			env[tc.key] = tc.input
			_, err := readConfig(envLookup(env), false)
			if err == nil || !strings.Contains(err.Error(), tc.key) {
				t.Fatalf("expected configuration refusal naming %s, got %v", tc.key, err)
			}
			if len(tc.input) > 5 && strings.Contains(err.Error(), tc.input) {
				t.Fatal("configuration refusal echoed rejected input")
			}
		})
	}
}

func TestConfigReadsTypedPolicyAndSecrets(t *testing.T) {
	t.Parallel()
	env := fixtureEnv()
	env["BUDGET_REQUEUE_SECONDS"] = "0"
	env["LEASE_SECONDS"] = "18"
	env["WORKERS"] = "7"
	cfg, err := readConfig(envLookup(env), false)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.databaseURL != env["DATABASE_URL"] || cfg.firestoreProject != env["FIRESTORE_PROJECT"] ||
		cfg.encryptionSecret != env["ENCRYPTION_SECRET"] {
		t.Fatal("runtime credentials and project were not loaded")
	}
	if cfg.policy.BudgetDelay != 0 || cfg.policy.Lease != 18*time.Second || cfg.policy.Workers != 7 ||
		cfg.healthPort != 8080 || cfg.metricsPort != 9090 || cfg.stopTimeout != 25*time.Second {
		t.Fatal("unexpected parsed queue or listener policy")
	}
}

func TestMigrationConfigUsesOnlyPostgresCredentials(t *testing.T) {
	t.Parallel()
	env := map[string]string{"DATABASE_URL": fixtureEnv()["DATABASE_URL"]}
	_, err := readConfig(envLookup(env), true)
	if err != nil {
		t.Fatal(err)
	}
}

func TestConfigAllowsTLSDisabledOnlyForLoopback(t *testing.T) {
	t.Parallel()
	for _, raw := range []string{
		"postgres://workerd:synthetic@localhost/queue?sslmode=disable",
		"postgres://workerd:synthetic@127.0.0.1/queue?sslmode=disable",
		"postgres://workerd:synthetic@[::1]/queue?sslmode=disable",
	} {
		t.Run(raw, func(t *testing.T) {
			t.Parallel()
			env := fixtureEnv()
			env["DATABASE_URL"] = raw
			if _, err := readConfig(envLookup(env), false); err != nil {
				t.Fatalf("loopback database URL should allow disabled TLS: %v", err)
			}
		})
	}
}

func TestEraseConfigPinsTheAuthoritativeFirestorePlane(t *testing.T) {
	t.Parallel()
	env := fixtureEnv()
	env["ERASE_PORT"] = "9443"
	env["ERASE_AUDIENCE"] = "synthetic-worker"
	env["ERASE_CALLER_SUBJECT"] = "123456"
	env["ERASE_TLS_CERT"] = "/dev/null"
	env["ERASE_TLS_KEY"] = "/dev/null"
	env["ERASE_FIRESTORE_PROJECT"] = "demo-marker-data"
	for _, db := range []string{"staging", "(default)"} {
		env["ERASE_FIRESTORE_DATABASE"] = db
		cfg, err := readConfig(envLookup(env), false)
		if err != nil {
			t.Fatal(err)
		}
		if cfg.erase.markerProject == cfg.firestoreProject ||
			cfg.erase.markerProject != "demo-marker-data" || cfg.erase.markerDatabase != db {
			t.Fatal("erase listener did not pin the authoritative marker database")
		}
	}
	for _, db := range []string{"", "databases/staging"} {
		env["ERASE_FIRESTORE_DATABASE"] = db
		if _, err := readConfig(envLookup(env), false); err == nil {
			t.Fatal("erase listener started without a valid explicit marker database")
		}
	}
	env["ERASE_FIRESTORE_DATABASE"] = "staging"
	delete(env, "ERASE_FIRESTORE_PROJECT")
	if _, err := readConfig(envLookup(env), false); err == nil {
		t.Fatal("erase listener started without a valid explicit marker project")
	}
}
